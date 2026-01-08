# routers/users.py
from fastapi import APIRouter, Depends, HTTPException
from database import get_db_connection
from pydantic import BaseModel
from config import settings
import httpx

# 创建路由器
router = APIRouter(prefix="/api/v1/users", tags=["Users"])

# 定义接收数据的模型
class UserOnboarding(BaseModel):
    loginCode: str   # 微信 wx.login 获取的临时 code
    steamId: str
    authCode: str
    matchCode: str

@router.post("/onboarding")
async def onboarding(data: UserOnboarding, db = Depends(get_db_connection)):
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
        with db.cursor() as cursor:
            # 方案：如果有这个OpenID就更新，没有就插入 (Upsert)
            sql = """
            INSERT INTO users (uuid, steam_id, auth_code, match_code)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                steam_id = VALUES(steam_id),
                auth_code = VALUES(auth_code),
                match_code = VALUES(match_code),
                updated_at = CURRENT_TIMESTAMP
            """
            cursor.execute(sql, (openid, data.steamId, data.authCode, data.matchCode))
        
        # 别忘了 database.py 里最好开启 autocommit=True，或者这里手动 commit
        db.commit() 
        
        return {
            "code": 200, 
            "message": "Binding Success", 
            "data": {"uuid": openid} # 返回 OpenID 给前端做缓存（可选）
        }

    except Exception as e:
        print(f"DB Error: {e}")
        raise HTTPException(status_code=500, detail="Database operation failed")