import asyncio
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import unquote, urlparse

import httpx


STEAM_API_BASE = "https://api.steampowered.com"
CS2_APP_ID = "730"
STEAM_ID64_RE = re.compile(r"^7656119\d{10}$")
PROFILE_RE = re.compile(r"steamcommunity\.com/profiles/(7656119\d{10})", re.IGNORECASE)
VANITY_RE = re.compile(r"steamcommunity\.com/id/([^/?#]+)", re.IGNORECASE)


def chunked(values: Iterable[str], size: int = 100) -> List[List[str]]:
    items = list(values)
    return [items[index:index + size] for index in range(0, len(items), size)]


def parse_steam_input(raw_value: str) -> Dict[str, str]:
    value = unquote(raw_value.strip())
    if STEAM_ID64_RE.fullmatch(value):
        return {"kind": "steamid64", "value": value}

    profile_match = PROFILE_RE.search(value)
    if profile_match:
        return {"kind": "steamid64", "value": profile_match.group(1)}

    vanity_match = VANITY_RE.search(value)
    if vanity_match:
        return {"kind": "vanity", "value": vanity_match.group(1).strip()}

    parsed = urlparse(value if "://" in value else f"https://{value}")
    if parsed.netloc and parsed.netloc.lower() not in {"steamcommunity.com", "www.steamcommunity.com"}:
        raise ValueError("只支持 Steam 社区个人资料链接")

    if re.fullmatch(r"[A-Za-z0-9_-]{2,64}", value):
        return {"kind": "vanity", "value": value}
    raise ValueError("无法识别 SteamID64、Profile URL 或 Vanity URL")


class SteamRadarClient:
    def __init__(self, api_key: str, timeout: float = 10.0, max_concurrency: int = 3):
        if not api_key:
            raise ValueError("STEAM_API_KEY is not configured")
        self.api_key = api_key
        self.timeout = timeout
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def _get(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        async with self._semaphore:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{STEAM_API_BASE}{path}",
                    params={"key": self.api_key, **params},
                )
                response.raise_for_status()
                return response.json()

    async def resolve(self, raw_value: str) -> Dict[str, Any]:
        parsed = parse_steam_input(raw_value)
        steam_id = parsed["value"]
        if parsed["kind"] == "vanity":
            payload = await self._get(
                "/ISteamUser/ResolveVanityURL/v1/",
                {"vanityurl": parsed["value"], "url_type": 1},
            )
            resolved = payload.get("response", {})
            if resolved.get("success") != 1 or not resolved.get("steamid"):
                raise ValueError("Steam 自定义链接不存在或不可解析")
            steam_id = str(resolved["steamid"])

        summaries = await self.get_summaries([steam_id])
        summary = summaries.get(steam_id, {})
        return {
            "steam_id": steam_id,
            "personaname": summary.get("personaname") or steam_id,
            "avatar_url": summary.get("avatarfull") or summary.get("avatarmedium"),
            "profile_url": summary.get("profileurl") or f"https://steamcommunity.com/profiles/{steam_id}/",
            "community_visibility_state": summary.get("communityvisibilitystate"),
        }

    async def get_summaries(self, steam_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        async def fetch(batch: List[str]) -> List[Dict[str, Any]]:
            payload = await self._get(
                "/ISteamUser/GetPlayerSummaries/v2/",
                {"steamids": ",".join(batch)},
            )
            return payload.get("response", {}).get("players", [])

        results = await asyncio.gather(*(fetch(batch) for batch in chunked(steam_ids, 100)))
        return {str(player["steamid"]): player for batch in results for player in batch}

    async def get_bans(self, steam_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        async def fetch(batch: List[str]) -> List[Dict[str, Any]]:
            payload = await self._get(
                "/ISteamUser/GetPlayerBans/v1/",
                {"steamids": ",".join(batch)},
            )
            return payload.get("players", [])

        results = await asyncio.gather(*(fetch(batch) for batch in chunked(steam_ids, 100)))
        return {str(player["SteamId"]): player for batch in results for player in batch}

    async def get_cs2_playtime(self, steam_id: str) -> Optional[int]:
        payload = await self._get(
            "/IPlayerService/GetOwnedGames/v1/",
            {
                "steamid": steam_id,
                "include_appinfo": "false",
                "include_played_free_games": "true",
                "appids_filter[0]": CS2_APP_ID,
            },
        )
        games = payload.get("response", {}).get("games", [])
        for game in games:
            if str(game.get("appid")) == CS2_APP_ID:
                return int(game.get("playtime_forever", 0))
        return None


def build_risk_signals(
    target: Dict[str, Any],
    summary: Dict[str, Any],
    bans: Dict[str, Any],
    cs2_playtime_minutes: Optional[int],
    now: Optional[datetime] = None,
) -> List[Dict[str, str]]:
    signals: List[Dict[str, str]] = []
    now = now or datetime.now(timezone.utc)

    manual_level = target.get("manual_cs_level")
    if manual_level is not None and int(manual_level) < 40:
        signals.append({"code": "cs_level_below_40", "severity": "high", "label": "CS 等级低于 40"})
    if target.get("service_medal") == "no":
        signals.append({"code": "no_service_medal", "severity": "high", "label": "人工标记：无服役勋章"})
    if bans.get("VACBanned") or int(bans.get("NumberOfGameBans", 0) or 0) > 0:
        signals.append({"code": "steam_ban", "severity": "high", "label": "存在 VAC 或游戏封禁"})

    visibility = summary.get("communityvisibilitystate")
    if visibility is not None and int(visibility) != 3:
        signals.append({"code": "private_profile", "severity": "info", "label": "Steam 资料不可见"})

    created_at = summary.get("timecreated")
    if created_at:
        age_days = (now - datetime.fromtimestamp(int(created_at), tz=timezone.utc)).days
        if age_days < 365:
            signals.append({"code": "young_account", "severity": "medium", "label": "Steam 账号不足一年"})
    if cs2_playtime_minutes is not None and cs2_playtime_minutes < 30000:
        signals.append({"code": "low_cs2_playtime", "severity": "medium", "label": "CS2 可见时长低于 500 小时"})
    return signals


def presence_from_summary(summary: Dict[str, Any]) -> Dict[str, Optional[str]]:
    game_id = str(summary.get("gameid")) if summary.get("gameid") is not None else None
    server_ip = summary.get("gameserverip") or None
    lobby_id = summary.get("lobbysteamid") or None
    if game_id == CS2_APP_ID and (server_ip or lobby_id):
        status = "in_match"
    elif game_id == CS2_APP_ID:
        status = "in_cs2"
    elif int(summary.get("personastate", 0) or 0) > 0:
        status = "online"
    else:
        status = "offline"
    group_key = f"lobby:{lobby_id}" if lobby_id else (f"server:{server_ip}" if server_ip else None)
    return {"status": status, "game_id": game_id, "server_ip": server_ip, "lobby_id": lobby_id, "group_key": group_key}
