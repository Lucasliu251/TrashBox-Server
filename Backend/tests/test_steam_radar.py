from datetime import datetime, timezone

import pytest

from services.steam_radar import (
    SteamRadarClient,
    build_risk_signals,
    chunked,
    parse_steam_input,
    presence_from_summary,
)


def test_parse_steamid_and_profile_urls():
    steam_id = "76561198000000000"
    assert parse_steam_input(steam_id) == {"kind": "steamid64", "value": steam_id}
    assert parse_steam_input(f"https://steamcommunity.com/profiles/{steam_id}/") == {
        "kind": "steamid64",
        "value": steam_id,
    }
    assert parse_steam_input("https://steamcommunity.com/id/lucas_cs2/") == {
        "kind": "vanity",
        "value": "lucas_cs2",
    }


def test_rejects_non_steam_profile_url():
    with pytest.raises(ValueError):
        parse_steam_input("https://example.com/id/not-steam")


def test_batches_presence_requests_at_100():
    ids = [str(76561198000000000 + index) for index in range(201)]
    assert [len(batch) for batch in chunked(ids)] == [100, 100, 1]


@pytest.mark.asyncio
async def test_get_summaries_merges_partial_batches():
    class FakeClient(SteamRadarClient):
        def __init__(self):
            super().__init__("test")
            self.batch_sizes = []

        async def _get(self, path, params):
            ids = params["steamids"].split(",")
            self.batch_sizes.append(len(ids))
            return {"response": {"players": [{"steamid": steam_id} for steam_id in ids[:-1]]}}

    client = FakeClient()
    steam_ids = [str(76561198000000000 + index) for index in range(101)]
    result = await client.get_summaries(steam_ids)
    assert sorted(client.batch_sizes) == [1, 100]
    assert len(result) == 99


def test_presence_and_same_match_grouping():
    presence = presence_from_summary({
        "gameid": "730",
        "gameserverip": "203.0.113.2:27015",
        "personastate": 1,
    })
    assert presence["status"] == "in_match"
    assert presence["group_key"] == "server:203.0.113.2:27015"
    assert presence_from_summary({"gameid": "730"})["status"] == "in_cs2"
    assert presence_from_summary({"personastate": 1})["status"] == "online"


def test_risk_signals_include_manual_level_bans_and_new_account():
    target = {"manual_cs_level": 12, "service_medal": "no"}
    summary = {
        "communityvisibilitystate": 3,
        "timecreated": int(datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp()),
    }
    bans = {"VACBanned": True, "NumberOfGameBans": 0}
    signals = build_risk_signals(
        target,
        summary,
        bans,
        cs2_playtime_minutes=1200,
        now=datetime(2026, 8, 10, tzinfo=timezone.utc),
    )
    codes = {signal["code"] for signal in signals}
    assert {"cs_level_below_40", "no_service_medal", "steam_ban", "young_account", "low_cs2_playtime"} <= codes


def test_low_playtime_signal_uses_1000_hour_boundary():
    below_threshold = build_risk_signals({}, {}, {}, cs2_playtime_minutes=59999)
    at_threshold = build_risk_signals({}, {}, {}, cs2_playtime_minutes=60000)

    assert any(signal["code"] == "low_cs2_playtime" and "1000" in signal["label"] for signal in below_threshold)
    assert all(signal["code"] != "low_cs2_playtime" for signal in at_threshold)
