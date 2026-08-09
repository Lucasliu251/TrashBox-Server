import base64
import binascii
import hashlib
import hmac
import json
import time
from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy import text

from config import settings
from database import get_db_connection


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_b64url(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def issue_access_token(user_uuid: str, ttl_seconds: Optional[int] = None) -> str:
    if not settings.JWT_SECRET:
        raise HTTPException(status_code=503, detail="JWT_SECRET is not configured")

    now = int(time.time())
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64url(json.dumps({
        "sub": user_uuid,
        "iat": now,
        "exp": now + (ttl_seconds or settings.JWT_TTL_SECONDS),
    }, separators=(",", ":")).encode())
    signing_input = f"{header}.{payload}".encode()
    signature = _b64url(hmac.new(settings.JWT_SECRET.encode(), signing_input, hashlib.sha256).digest())
    return f"{header}.{payload}.{signature}"


def decode_access_token(token: str) -> str:
    if not settings.JWT_SECRET:
        raise HTTPException(status_code=503, detail="JWT_SECRET is not configured")
    try:
        header, payload, signature = token.split(".")
        signing_input = f"{header}.{payload}".encode()
        expected = _b64url(hmac.new(settings.JWT_SECRET.encode(), signing_input, hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("bad signature")
        decoded = json.loads(_decode_b64url(payload))
        if int(decoded["exp"]) <= int(time.time()):
            raise ValueError("expired")
        return str(decoded["sub"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError, binascii.Error, UnicodeDecodeError):
        raise HTTPException(status_code=401, detail="Invalid or expired access token")


def get_current_user(
    authorization: Optional[str] = Header(default=None),
    connection=Depends(get_db_connection),
) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    user_uuid = decode_access_token(authorization[7:].strip())
    exists = connection.execute(
        text("SELECT 1 FROM users WHERE uuid = :uuid LIMIT 1"),
        {"uuid": user_uuid},
    ).fetchone()
    if not exists:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return user_uuid
