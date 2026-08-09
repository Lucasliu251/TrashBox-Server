import hashlib
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import text

from config import settings
from database import get_db_connection
from services.auth import get_current_user, issue_access_token


router = APIRouter(prefix="/api/v1/web-auth", tags=["Web Auth"])


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _create_challenge(connection, status: str = "pending", user_uuid: str = None):
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(minutes=5)
    connection.execute(text("""
        INSERT INTO web_login_challenges (token_hash, status, user_uuid, expires_at)
        VALUES (:token_hash, :status, :user_uuid, :expires_at)
    """), {
        "token_hash": _token_hash(token),
        "status": status,
        "user_uuid": user_uuid,
        "expires_at": expires_at,
    })
    connection.commit()
    return token, expires_at


@router.post("/challenges")
def create_challenge(connection=Depends(get_db_connection)):
    token, expires_at = _create_challenge(connection)
    return {
        "code": 201,
        "data": {
            "challenge_token": token,
            "qr_payload": f"trashbox://web-login/{token}",
            "expires_at": expires_at.isoformat() + "Z",
        },
    }


@router.get("/challenges/{token}")
def poll_challenge(token: str, connection=Depends(get_db_connection)):
    row = connection.execute(text("""
        SELECT status, user_uuid, expires_at, consumed_at
        FROM web_login_challenges WHERE token_hash = :token_hash
    """), {"token_hash": _token_hash(token)}).fetchone()
    if not row or row.expires_at <= datetime.utcnow():
        raise HTTPException(status_code=410, detail="Login challenge expired")
    if row.status != "confirmed":
        return {"code": 200, "data": {"status": row.status}}
    if row.consumed_at:
        raise HTTPException(status_code=410, detail="Login challenge already consumed")
    access_token = issue_access_token(row.user_uuid)
    connection.execute(text("""
        UPDATE web_login_challenges SET status = 'consumed', consumed_at = UTC_TIMESTAMP()
        WHERE token_hash = :token_hash AND consumed_at IS NULL
    """), {"token_hash": _token_hash(token)})
    connection.commit()
    return {"code": 200, "data": {"status": "confirmed", "access_token": access_token}}


@router.post("/challenges/{token}/confirm")
def confirm_challenge(token: str, user=Depends(get_current_user), connection=Depends(get_db_connection)):
    result = connection.execute(text("""
        UPDATE web_login_challenges SET status = 'confirmed', user_uuid = :user_uuid
        WHERE token_hash = :token_hash AND status = 'pending' AND expires_at > UTC_TIMESTAMP()
    """), {"token_hash": _token_hash(token), "user_uuid": user})
    connection.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=409, detail="Challenge expired or already used")
    return {"code": 200, "message": "Web login confirmed"}


@router.get("/steam/login")
def steam_login():
    if not settings.BASE_URL:
        raise HTTPException(status_code=503, detail="BASE_URL is not configured")
    return_to = f"{settings.BASE_URL.rstrip('/')}/api/v1/web-auth/steam/callback"
    params = {
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.mode": "checkid_setup",
        "openid.return_to": return_to,
        "openid.realm": settings.BASE_URL.rstrip("/"),
        "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
        "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
    }
    return RedirectResponse(f"https://steamcommunity.com/openid/login?{urlencode(params)}")


@router.get("/steam/callback")
async def steam_callback(request: Request, connection=Depends(get_db_connection)):
    params = dict(request.query_params)
    claimed_id = params.get("openid.claimed_id", "")
    if not claimed_id.startswith("https://steamcommunity.com/openid/id/"):
        raise HTTPException(status_code=400, detail="Invalid Steam OpenID response")
    verification = {**params, "openid.mode": "check_authentication"}
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post("https://steamcommunity.com/openid/login", data=verification)
    if "is_valid:true" not in response.text:
        raise HTTPException(status_code=401, detail="Steam OpenID verification failed")
    steam_id = claimed_id.rsplit("/", 1)[-1]
    user = connection.execute(text("SELECT uuid FROM users WHERE steam_id = :steam_id LIMIT 1"), {"steam_id": steam_id}).fetchone()
    if not user:
        raise HTTPException(status_code=403, detail="This Steam account is not linked to a TrashBox user")
    token, _expires_at = _create_challenge(connection, status="confirmed", user_uuid=user.uuid)
    return RedirectResponse(f"{settings.WEB_ORIGIN}/auth/callback?code={token}")
