import time

import pytest
from fastapi import HTTPException

from config import settings
from services.auth import decode_access_token, issue_access_token


def test_access_token_round_trip(monkeypatch):
    monkeypatch.setattr(settings, "JWT_SECRET", "unit-test-secret")
    token = issue_access_token("wx-user-1", ttl_seconds=60)
    assert decode_access_token(token) == "wx-user-1"


def test_access_token_rejects_tampering(monkeypatch):
    monkeypatch.setattr(settings, "JWT_SECRET", "unit-test-secret")
    token = issue_access_token("wx-user-1", ttl_seconds=60)
    replacement = "A" if token[-1] != "A" else "B"
    with pytest.raises(HTTPException) as exc:
        decode_access_token(token[:-1] + replacement)
    assert exc.value.status_code == 401


def test_access_token_rejects_expired_token(monkeypatch):
    monkeypatch.setattr(settings, "JWT_SECRET", "unit-test-secret")
    token = issue_access_token("wx-user-1", ttl_seconds=-1)
    time.sleep(0.01)
    with pytest.raises(HTTPException) as exc:
        decode_access_token(token)
    assert exc.value.status_code == 401
