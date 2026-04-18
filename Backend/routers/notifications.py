from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from database import get_db_connection
import httpx
from config import settings # 确保你有 WX_APP_ID 和 WX_APP_SECRET

router = APIRouter(prefix="/api/v1/notifications", tags=["Notifications"])

class SubscribeReq(BaseModel):
    openid: str
    template_id: str

@router.post("/subscribe")
def user_subscribe(req: SubscribeReq, connection=Depends(get_db_connection)):
    # 记录用户的订阅，remaining_count + 1
    sql = text("""
        INSERT INTO subscriptions (openid, template_id, remaining_count)
        VALUES (:oid, :tid, 1)
        ON DUPLICATE KEY UPDATE remaining_count = remaining_count + 1
    """)
    connection.execute(sql, {"oid": req.openid, "tid": req.template_id})
    connection.commit()
    return {"code": 200, "message": "Subscribed"}
