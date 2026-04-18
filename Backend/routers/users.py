# routers/users.py
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query
from sqlalchemy import text
from database import get_db_connection
from pydantic import BaseModel
from config import settings
from typing import Optional
import os
import re
import uuid
import shutil
import requests
import httpx

# 创建路由器
router = APIRouter(prefix="/api/v1/users", tags=["Users"])

# 定义接收数据的模型
class UserOnboarding(BaseModel):
    loginCode: str   # 微信 wx.login 获取的临时 code
    steamId: str
    authCode: str
    matchCode: str

class UserLogin(BaseModel):
    loginCode: str

class UserUpdate(BaseModel):
    openid: str
    nickname: Optional[str] = None
    avatar: Optional[str] = None

@router.post("/login")
async def login(data: UserLogin, connection=Depends(get_db_connection)):
    # 1. 拿 code 换 OpenID (和注册时的逻辑一样)
    async with httpx.AsyncClient() as client:
        wx_url = "https://api.weixin.qq.com/sns/jscode2session"
        params = {
            "appid": settings.WX_APP_ID,
            "secret": settings.WX_APP_SECRET,
            "js_code": data.loginCode,
            "grant_type": "authorization_code"
        }
        response = await client.get(wx_url, params=params)
        wx_res = response.json()

    if "errcode" in wx_res and wx_res["errcode"] != 0:
        raise HTTPException(status_code=400, detail=f"WeChat API Error: {wx_res.get('errmsg')}")

    openid = wx_res["openid"]

    # 2. 查数据库：这个人注册过吗？
    try:
        # 只要查 steam_id 即可，不用查全部
        sql = text("SELECT steam_id FROM users WHERE uuid = :uuid")
        row = connection.execute(sql, {"uuid": openid}).fetchone()

        if row:
            # 【已注册】返回用户信息
            # 注意：row.steam_id 可能是 None，虽然理论上注册流程保证了它存在
            return {
                "code": 200,
                "message": "Login Success",
                "data": {
                    "is_registered": True,
                    "uuid": openid,
                    "steam_id": row.steam_id
                }
            }
        else:
            # 【未注册】告诉前端去注册
            return {
                "code": 200, # 状态码还是200，通过内部逻辑判断
                "message": "User Not Registered",
                "data": {
                    "is_registered": False,
                    "uuid": openid 
                }
            }

    except Exception as e:
        print(f"Login DB Error: {e}")
        raise HTTPException(status_code=500, detail="Database error during login")

@router.post("/onboarding")
async def onboarding(data: UserOnboarding, connection = Depends(get_db_connection)):
    #0. 智能解析 Steam ID
    try:
        # 将用户输入的各种乱七八糟的格式，清洗为标准的 real_steam_id
        real_steam_id = await resolve_steam_id_task(data.steamId)
        print(f"SteamID Resolved: {data.steamId} -> {real_steam_id}")
    except ValueError as ve:
        # 解析失败，返回 400 给前端提示用户
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        print(f"Resolve Error: {e}")
        raise HTTPException(status_code=400, detail="无法识别 Steam ID，请尝试直接输入数字 ID")
    
    # 1. 向微信服务器发起请求，换取 OpenID
    async with httpx.AsyncClient() as client:
        wx_url = "https://api.weixin.qq.com/sns/jscode2session"
        params = {
            "appid": settings.WX_APP_ID,
            "secret": settings.WX_APP_SECRET,
            "js_code": data.loginCode,
            "grant_type": "authorization_code"
        }
        response = await client.get(wx_url, params=params)
        wx_res = response.json()

    # 检查微信是否返回错误
    if "errcode" in wx_res and wx_res["errcode"] != 0:
        raise HTTPException(status_code=400, detail=f"WeChat Login Failed: {wx_res.get('errmsg')}")

    # 获取到了真正的 OpenID
    openid = wx_res["openid"]
    # session_key = wx_res["session_key"] # 如果以后要解密手机号需要这个，现在暂时不用

    print(f"User Login: OpenID={openid}, SteamID={real_steam_id}")

    # 2. 存入数据库
    try:
        # [修改] 使用 text() 包裹 SQL，并将 %s 改为 :占位符
        sql = text("""
            INSERT INTO users (uuid, steam_id, auth_code, match_code)
            VALUES (:uuid, :steam_id, :auth_code, :match_code)
            ON DUPLICATE KEY UPDATE
                steam_id = VALUES(steam_id),
                auth_code = VALUES(auth_code),
                match_code = VALUES(match_code),
                updated_at = CURRENT_TIMESTAMP
        """)
        
        # [修改] execute 直接传参数字典
        connection.execute(sql, {
            "uuid": openid,
            "steam_id": real_steam_id,
            "auth_code": data.authCode,
            "match_code": data.matchCode
        })
        
        # [修改] SQLAlchemy 需要手动提交
        connection.commit() 
        
        return {
            "code": 200, 
            "message": "Binding Success", 
            "data": {"uuid": openid, "steam_id": real_steam_id} 
        }

    except Exception as e:
        print(f"DB Error: {e}")
        raise HTTPException(status_code=500, detail="Database operation failed")

# 获取用户个人资料
@router.get("/me")
async def get_my_profile(openid: str, connection = Depends(get_db_connection)):
    # 注意：实际生产中 openid 应该从 Header 的 Token 解析，现在开发阶段我们先通过参数传
    try:
        sql = text("SELECT uuid, steam_id, auth_code, match_code, avatar, nickname, canEdit, created_at FROM users WHERE uuid = :uuid")
        
        result = connection.execute(sql, {"uuid": openid}).fetchone()
            
        if not result:
            return {"code": 404, "message": "User not found"}
        
        # [修改] 将 SQLAlchemy 的 Row 对象转换为字典
        # SQLAlchemy 1.4+ 推荐使用 dict(row._mapping)
        user_data = dict(result._mapping)
            
        return {
            "code": 200, 
            "data": user_data
        }
    except Exception as e:
        print(f"Error fetching profile: {e}")
        return {"code": 500, "message": str(e)}
    
# 更新用户信息接口
@router.put("/update")
async def update_user_profile(data: UserUpdate, connection=Depends(get_db_connection)):
    try:
        # 1. 动态构建 SQL，只更新前端传过来的字段
        # 这样更灵活，以后加字段不用改太多逻辑
        update_fields = []
        params = {"uuid": data.openid}

        if data.nickname is not None:
            update_fields.append("nickname = :nickname")
            params["nickname"] = data.nickname
        
        if data.avatar is not None:
            update_fields.append("avatar = :avatar")
            params["avatar"] = data.avatar

        # 如果没有要更新的字段，直接返回
        if not update_fields:
            return {"code": 400, "message": "No fields to update"}

        # 拼接 SQL
        sql_str = f"UPDATE users SET {', '.join(update_fields)}, updated_at = CURRENT_TIMESTAMP WHERE uuid = :uuid"
        
        # 2. 执行更新
        result = connection.execute(text(sql_str), params)
        connection.commit()

        # 检查是否有行被影响 (是否真的找到了用户并更新了)
        if result.rowcount == 0:
             # 虽然没报错，但可能 UUID 不对
             return {"code": 404, "message": "User not found or no changes made"}

        return {"code": 200, "message": "Profile updated successfully"}

    except Exception as e:
        print(f"Update Profile Error: {e}")
        raise HTTPException(status_code=500, detail="Database update failed")
    

# 上传用户头像接口
# 确保图片保存目录存在
UPLOAD_DIR = "assets/avatars"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/avatar")
async def upload_avatar(file: UploadFile = File(...)):
    try:
        # 1. 验证文件类型 (可选)
        if not file.content_type.startswith("image/"):
            return {"code": 400, "message": "Only image files are allowed"}

        # 2. 生成唯一文件名 (防止重名覆盖)
        file_ext = os.path.splitext(file.filename)[1] # 获取后缀 .jpg/.png
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        file_path = os.path.join(UPLOAD_DIR, unique_filename)

        # 3. 保存文件到硬盘
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 4. 生成可访问的 URL
        # 注意：这里需要你的服务器 IP 或域名。假设 apiBase 是 http://47.115.75.168:8000
        # 最终 URL 类似: http://47.115.75.168:8000/static/avatars/xxxx.jpg
        # 建议在 settings.py 里配置 BASE_URL，这里先用 request.base_url 的逻辑或者硬编码
        
        # 简单拼接路径 (前端 apiBase 后面拼上这个 relative path)
        relative_url = f"/assets/avatars/{unique_filename}"
        
        # 如果你想返回绝对路径，可以拼上 host
        full_url = f"{settings.BASE_URL}{relative_url}" # 假设端口是8000

        return {
            "code": 200, 
            "message": "Upload success", 
            "url": full_url
        }

    except Exception as e:
        print(f"Upload Error: {e}")
        raise HTTPException(status_code=500, detail="File upload failed")
    

@router.get("/search")
def search_users(
    q: str = Query(..., min_length=1, description="搜索关键词：昵称或SteamID"),
    connection = Depends(get_db_connection)
):
    keyword = f"%{q}%" # 模糊匹配模式
    
    # 1. 搜索 Users 表 (已注册用户)
    # 优先匹配 steam_id 精确查找，或者 nickname 模糊查找
    sql_users = text("""
        SELECT steam_id, nickname, avatar 
        FROM users 
        WHERE steam_id = :exact_id OR nickname LIKE :like_name
        LIMIT 5
    """)
    
    # 2. 搜索 Daily 表 (未注册但在榜单上的历史用户)
    # 使用 DISTINCT 去重，因为 daily 表有很多天的数据
    sql_daily = text("""
        SELECT DISTINCT steam_id, nickname 
        FROM daily 
        WHERE steam_id = :exact_id OR nickname LIKE :like_name
        LIMIT 5
    """)
    
    params = {"exact_id": q, "like_name": keyword}
    
    rows_users = connection.execute(sql_users, params).fetchall()
    rows_daily = connection.execute(sql_daily, params).fetchall()
    
    # 3. 数据合并与去重 (以 SteamID 为键)
    results = {}
    
    # 先放入注册用户 (优先级高)
    for row in rows_users:
        results[row.steam_id] = {
            "steam_id": row.steam_id,
            "nickname": row.nickname,
            "avatar": row.avatar,
            "source": "registered"
        }
        
    # 再放入历史用户 (如果已存在则跳过，保证优先显示注册信息)
    for row in rows_daily:
        if row.steam_id not in results:
            results[row.steam_id] = {
                "steam_id": row.steam_id,
                "nickname": row.nickname,
                "avatar": None, # 历史用户没有自定义头像
                "source": "history"
            }
            
    # 转为列表返回
    return {"code": 200, "data": list(results.values())}




# 解析 Steam ID 的辅助函数
async def resolve_steam_id_task(input_str: str) -> str:
    input_str = input_str.strip()
    
    # 情况 A: 用户直接输入了 17 位纯数字 ID (SteamID64)
    # 这是最理想的情况，直接返回
    if input_str.isdigit() and len(input_str) == 17:
        return input_str
        
    # 情况 B: 用户输入了包含 profiles 的链接
    # 例如: https://steamcommunity.com/profiles/76561198xxxxxxxxx/
    # 正则提取 /profiles/ 后面的数字
    profile_pattern = r"steamcommunity\.com/profiles/(\d{17})"
    match = re.search(profile_pattern, input_str)
    if match:
        return match.group(1)
        
    # 情况 C: 用户输入了自定义 URL (Vanity URL) 或者 纯自定义名
    # 例如: https://steamcommunity.com/id/lucas_cs2/ 或 lucas_cs2
    vanity_name = None
    
    # 尝试从链接提取名字
    vanity_pattern = r"steamcommunity\.com/id/([^/]+)"
    match_vanity = re.search(vanity_pattern, input_str)
    
    if match_vanity:
        vanity_name = match_vanity.group(1)
    elif not input_str.isdigit() and "/" not in input_str: 
        # 假设用户只输了自定义id的名字 (如 "lucas_cs2")，没有输链接
        vanity_name = input_str
        
    if vanity_name:
        # 调用 Steam 官方 API 将自定义名字转为 ID64
        url = "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v0001/"
        params = {
            "key": settings.STEAM_API_KEY, # 必填：你的 Steam API Key
            "vanityurl": vanity_name
        }
        
        async with httpx.AsyncClient() as client:
            try:
                res = await client.get(url, params=params, timeout=10.0)
                data = res.json()
                
                if data.get('response', {}).get('success') == 1:
                    return data['response']['steamid']
                else:
                    raise ValueError("无法解析该自定义ID，请检查拼写")
            except Exception as e:
                print(f"Steam API Error: {e}")
                # 如果 Steam API 挂了或者超时，抛出异常让用户直接输 ID
                raise ValueError("连接 Steam 服务器失败，请直接输入 17 位数字 ID")

    # 如果以上都不匹配
    raise ValueError("无效的 Steam ID 格式，请复制个人主页链接或输入 17 位 ID")