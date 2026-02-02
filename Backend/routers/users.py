# routers/users.py
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy import text
from database import get_db_connection
from pydantic import BaseModel
from config import settings
from typing import Optional
import os
import uuid
import shutil
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

    print(f"User Login: OpenID={openid}, SteamID={data.steamId}")

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
            "steam_id": data.steamId,
            "auth_code": data.authCode,
            "match_code": data.matchCode
        })
        
        # [修改] SQLAlchemy 需要手动提交
        connection.commit() 
        
        return {
            "code": 200, 
            "message": "Binding Success", 
            "data": {"uuid": openid} 
        }

    except Exception as e:
        print(f"DB Error: {e}")
        raise HTTPException(status_code=500, detail="Database operation failed")

# 获取用户个人资料
@router.get("/me")
async def get_my_profile(openid: str, connection = Depends(get_db_connection)):
    # 注意：实际生产中 openid 应该从 Header 的 Token 解析，现在开发阶段我们先通过参数传
    try:
        sql = text("SELECT uuid, steam_id, auth_code, match_code, avatar, nickname, created_at FROM users WHERE uuid = :uuid")
        
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