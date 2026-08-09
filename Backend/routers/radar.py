import asyncio
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from config import settings
from database import engine, get_db_connection
from models.radar import RadarSessionCreate, RadarTargetCreate, RadarTargetUpdate, ResolveRequest
from services.auth import get_current_user
from services.steam_radar import SteamRadarClient, build_risk_signals, presence_from_summary


router = APIRouter(prefix="/api/v1/radar", tags=["Radar"])
_scan_lock = asyncio.Lock()
_active_task: Optional[asyncio.Task] = None
_last_snapshot_monotonic = 0.0


def _model_dump(model, **kwargs):
    if hasattr(model, "model_dump"):
        return model.model_dump(**kwargs)
    return model.dict(**kwargs)


def _json_value(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _serialize_datetime(value: Any) -> Any:
    return value.isoformat() + ("Z" if value.tzinfo is None else "") if isinstance(value, datetime) else value


def _load_targets(connection) -> List[Dict[str, Any]]:
    rows = connection.execute(text("""
        SELECT t.*,
               o.status, o.personaname, o.avatar_url, o.profile_url,
               o.privacy_state, o.persona_state, o.game_id, o.game_extra_info,
               o.game_server_ip, o.lobby_steam_id, o.group_key,
               o.account_created_at, o.cs2_playtime_minutes,
               o.vac_banned, o.game_ban_count, o.risk_signals, o.observed_at
        FROM radar_targets t
        LEFT JOIN radar_observations o ON o.id = (
            SELECT MAX(latest.id) FROM radar_observations latest WHERE latest.target_id = t.id
        )
        ORDER BY
            CASE o.status WHEN 'in_match' THEN 0 WHEN 'in_cs2' THEN 1 WHEN 'online' THEN 2 ELSE 3 END,
            COALESCE(t.alias, o.personaname, t.steam_id)
    """)).fetchall()
    result = []
    for row in rows:
        item = dict(row._mapping)
        item["tags"] = _json_value(item.get("tags"), [])
        item["risk_signals"] = _json_value(item.get("risk_signals"), [])
        for key in ("created_at", "updated_at", "account_created_at", "observed_at"):
            item[key] = _serialize_datetime(item.get(key))
        result.append(item)
    return result


def _active_session(connection) -> Optional[Dict[str, Any]]:
    connection.execute(text("""
        UPDATE radar_sessions SET status = 'expired'
        WHERE status = 'active' AND expires_at <= UTC_TIMESTAMP()
    """))
    row = connection.execute(text("""
        SELECT * FROM radar_sessions
        WHERE status = 'active' AND expires_at > UTC_TIMESTAMP()
        ORDER BY started_at DESC LIMIT 1
    """)).fetchone()
    if not row:
        return None
    data = dict(row._mapping)
    for key in ("started_at", "expires_at", "last_tick_at"):
        data[key] = _serialize_datetime(data.get(key))
    return data


def _scan_targets(connection) -> List[Dict[str, Any]]:
    rows = connection.execute(text("""
        SELECT t.*,
               o.cs2_playtime_minutes AS cached_playtime,
               o.observed_at AS cached_at
        FROM radar_targets t
        LEFT JOIN radar_observations o ON o.id = (
            SELECT MAX(latest.id) FROM radar_observations latest
            WHERE latest.target_id = t.id AND latest.cs2_playtime_minutes IS NOT NULL
        )
        ORDER BY t.id
    """)).fetchall()
    return [dict(row._mapping) for row in rows]


def _has_fresh_snapshot(connection, max_age_seconds: int = 15) -> bool:
    latest = connection.execute(text("SELECT MAX(observed_at) FROM radar_observations")).scalar()
    return bool(latest and (datetime.utcnow() - latest).total_seconds() < max_age_seconds)


async def _perform_scan(connection, session_id: Optional[str] = None) -> Dict[str, Any]:
    targets = _scan_targets(connection)
    if not targets:
        return {"observed": 0, "errors": [], "observed_at": datetime.now(timezone.utc).isoformat()}

    try:
        client = SteamRadarClient(settings.STEAM_API_KEY)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    steam_ids = [str(target["steam_id"]) for target in targets]
    errors: List[str] = []
    try:
        summaries = await client.get_summaries(steam_ids)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Steam presence query failed: {exc}")
    try:
        bans = await client.get_bans(steam_ids)
    except Exception as exc:
        bans = {}
        errors.append(f"ban data unavailable: {exc}")

    now = datetime.now(timezone.utc)
    stale_targets = []
    playtimes: Dict[str, Optional[int]] = {}
    for target in targets:
        cached_at = target.get("cached_at")
        cached_value = target.get("cached_playtime")
        if cached_value is not None:
            playtimes[str(target["steam_id"])] = int(cached_value)
        if not cached_at or now.replace(tzinfo=None) - cached_at > timedelta(hours=24):
            stale_targets.append(target)

    async def refresh_playtime(target: Dict[str, Any]) -> None:
        steam_id = str(target["steam_id"])
        try:
            playtimes[steam_id] = await client.get_cs2_playtime(steam_id)
        except Exception:
            playtimes.setdefault(steam_id, None)

    await asyncio.gather(*(refresh_playtime(target) for target in stale_targets[:30]))

    insert_sql = text("""
        INSERT INTO radar_observations (
            target_id, session_id, status, personaname, avatar_url, profile_url,
            privacy_state, persona_state, game_id, game_extra_info,
            game_server_ip, lobby_steam_id, group_key, account_created_at,
            cs2_playtime_minutes, vac_banned, game_ban_count, risk_signals, observed_at
        ) VALUES (
            :target_id, :session_id, :status, :personaname, :avatar_url, :profile_url,
            :privacy_state, :persona_state, :game_id, :game_extra_info,
            :game_server_ip, :lobby_steam_id, :group_key, :account_created_at,
            :cs2_playtime_minutes, :vac_banned, :game_ban_count, :risk_signals, UTC_TIMESTAMP()
        )
    """)
    for target in targets:
        steam_id = str(target["steam_id"])
        summary = summaries.get(steam_id, {})
        ban = bans.get(steam_id, {})
        presence = presence_from_summary(summary)
        created_at = summary.get("timecreated")
        risk_signals = build_risk_signals(target, summary, ban, playtimes.get(steam_id))
        connection.execute(insert_sql, {
            "target_id": target["id"],
            "session_id": session_id,
            "status": presence["status"] if summary else "unknown",
            "personaname": summary.get("personaname"),
            "avatar_url": summary.get("avatarfull") or summary.get("avatarmedium"),
            "profile_url": summary.get("profileurl"),
            "privacy_state": summary.get("communityvisibilitystate"),
            "persona_state": summary.get("personastate"),
            "game_id": presence["game_id"],
            "game_extra_info": summary.get("gameextrainfo"),
            "game_server_ip": presence["server_ip"],
            "lobby_steam_id": presence["lobby_id"],
            "group_key": presence["group_key"],
            "account_created_at": datetime.utcfromtimestamp(int(created_at)) if created_at else None,
            "cs2_playtime_minutes": playtimes.get(steam_id),
            "vac_banned": ban.get("VACBanned") if ban else None,
            "game_ban_count": ban.get("NumberOfGameBans") if ban else None,
            "risk_signals": json.dumps(risk_signals, ensure_ascii=False),
        })

    if session_id:
        connection.execute(text("""
            UPDATE radar_sessions
            SET last_tick_at = UTC_TIMESTAMP(), error_summary = :error_summary
            WHERE id = :session_id
        """), {"session_id": session_id, "error_summary": "; ".join(errors)[:500] or None})
    return {"observed": len(targets), "errors": errors, "observed_at": now.isoformat()}


async def _run_session(session_id: str) -> None:
    global _active_task
    try:
        while True:
            with engine.begin() as connection:
                row = connection.execute(text("SELECT status, expires_at FROM radar_sessions WHERE id = :id"), {"id": session_id}).fetchone()
                if not row or row.status != "active" or row.expires_at <= datetime.utcnow():
                    break
                try:
                    await _perform_scan(connection, session_id=session_id)
                except Exception as exc:
                    connection.execute(text("UPDATE radar_sessions SET error_summary = :error WHERE id = :id"), {
                        "id": session_id,
                        "error": str(exc)[:500],
                    })
            await asyncio.sleep(settings.RADAR_SCAN_INTERVAL_SECONDS)
        with engine.begin() as connection:
            connection.execute(text("""
                UPDATE radar_sessions SET status = 'completed'
                WHERE id = :id AND status = 'active'
            """), {"id": session_id})
    finally:
        _active_task = None


@router.post("/resolve")
async def resolve_target(data: ResolveRequest, _user=Depends(get_current_user)):
    if not settings.STEAM_API_KEY:
        raise HTTPException(status_code=503, detail="STEAM_API_KEY is not configured")
    try:
        return {"code": 200, "data": await SteamRadarClient(settings.STEAM_API_KEY).resolve(data.value)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Steam lookup failed: {exc}")


@router.get("/targets")
def list_targets(_user=Depends(get_current_user), connection=Depends(get_db_connection)):
    return {"code": 200, "data": _load_targets(connection)}


@router.post("/targets")
def create_target(data: RadarTargetCreate, user=Depends(get_current_user), connection=Depends(get_db_connection)):
    count = connection.execute(text("SELECT COUNT(*) FROM radar_targets")).scalar() or 0
    if count >= 2000:
        raise HTTPException(status_code=409, detail="Radar watchlist limit reached")
    try:
        connection.execute(text("""
            INSERT INTO radar_targets (steam_id, alias, tags, note, manual_cs_level, service_medal, added_by)
            VALUES (:steam_id, :alias, :tags, :note, :manual_cs_level, :service_medal, :added_by)
        """), {
            **_model_dump(data, exclude={"tags"}),
            "tags": json.dumps(data.tags, ensure_ascii=False),
            "added_by": user,
        })
        connection.commit()
    except Exception as exc:
        connection.rollback()
        if "Duplicate" in str(exc) or "uq_radar_targets" in str(exc):
            raise HTTPException(status_code=409, detail="该 Steam 用户已在监控名单中")
        raise
    return {"code": 201, "message": "Radar target added"}


@router.patch("/targets/{target_id}")
def update_target(target_id: int, data: RadarTargetUpdate, _user=Depends(get_current_user), connection=Depends(get_db_connection)):
    values = _model_dump(data, exclude_unset=True)
    if not values:
        raise HTTPException(status_code=400, detail="No fields to update")
    if "tags" in values:
        values["tags"] = json.dumps(values["tags"], ensure_ascii=False)
    assignments = ", ".join(f"{field} = :{field}" for field in values)
    result = connection.execute(text(f"UPDATE radar_targets SET {assignments} WHERE id = :target_id"), {
        **values,
        "target_id": target_id,
    })
    connection.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Radar target not found")
    return {"code": 200, "message": "Radar target updated"}


@router.delete("/targets/{target_id}")
def delete_target(target_id: int, _user=Depends(get_current_user), connection=Depends(get_db_connection)):
    result = connection.execute(text("DELETE FROM radar_targets WHERE id = :id"), {"id": target_id})
    connection.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Radar target not found")
    return {"code": 200, "message": "Radar target removed"}


@router.post("/snapshot")
async def snapshot(_user=Depends(get_current_user), connection=Depends(get_db_connection)):
    global _last_snapshot_monotonic
    active = _active_session(connection)
    connection.commit()
    if active and active.get("last_tick_at"):
        return {"code": 200, "data": {"coalesced": True, "session": active, "targets": _load_targets(connection)}}

    async with _scan_lock:
        if time.monotonic() - _last_snapshot_monotonic < 15 or _has_fresh_snapshot(connection):
            return {"code": 200, "data": {"coalesced": True, "session": active, "targets": _load_targets(connection)}}
        scan = await _perform_scan(connection, session_id=active["id"] if active else None)
        connection.commit()
        _last_snapshot_monotonic = time.monotonic()
    return {"code": 200, "data": {"coalesced": False, "scan": scan, "session": active, "targets": _load_targets(connection)}}


@router.get("/sessions")
def get_session(_user=Depends(get_current_user), connection=Depends(get_db_connection)):
    session = _active_session(connection)
    connection.commit()
    return {"code": 200, "data": session}


@router.post("/sessions")
async def start_session(data: RadarSessionCreate, user=Depends(get_current_user), connection=Depends(get_db_connection)):
    global _active_task
    active = _active_session(connection)
    if active:
        connection.commit()
        return {"code": 200, "data": active, "joined": True}

    session_id = str(uuid.uuid4())
    duration = min(data.duration_seconds, settings.RADAR_SESSION_SECONDS)
    expires_at = datetime.utcnow() + timedelta(seconds=duration)
    connection.execute(text("""
        INSERT INTO radar_sessions (id, mode, status, started_by, started_at, expires_at)
        VALUES (:id, 'continuous', 'active', :started_by, UTC_TIMESTAMP(), :expires_at)
    """), {"id": session_id, "started_by": user, "expires_at": expires_at})
    connection.commit()
    _active_task = asyncio.create_task(_run_session(session_id))
    return {"code": 201, "data": _active_session(connection), "joined": False}
