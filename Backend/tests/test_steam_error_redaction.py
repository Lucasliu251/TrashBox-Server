import unittest
from unittest.mock import patch

import httpx
from fastapi import HTTPException

from routers import radar
from services.steam_radar import SteamAPIError, SteamRadarClient


class DeniedHTTPClient:
    def __init__(self, timeout):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def get(self, url, params):
        request = httpx.Request('GET', url, params=params)
        httpx.Response(403, request=request).raise_for_status()


class DeniedSteamClient:
    def __init__(self, key):
        pass

    async def get_summaries(self, steam_ids):
        raise SteamAPIError(403)


class SteamErrorRedactionTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_error_never_exposes_key_or_url(self):
        with patch('services.steam_radar.httpx.AsyncClient', DeniedHTTPClient):
            with self.assertRaises(SteamAPIError) as result:
                await SteamRadarClient('dummy-secret-for-test').get_summaries(['76561198000000000'])
        self.assertEqual(result.exception.status_code, 403)
        self.assertNotIn('dummy-secret-for-test', str(result.exception))
        self.assertNotIn('http', str(result.exception))

    async def test_radar_response_never_exposes_key_or_url(self):
        with patch.object(radar, '_scan_targets', return_value=[{'steam_id': '76561198000000000'}]), \
             patch.object(radar, 'SteamRadarClient', DeniedSteamClient), \
             patch.object(radar.settings, 'STEAM_API_KEY', 'dummy-secret-for-test'):
            with self.assertRaises(HTTPException) as result:
                await radar._perform_scan(object())
        self.assertEqual(result.exception.status_code, 502)
        self.assertIn('403', result.exception.detail)
        self.assertNotIn('dummy-secret-for-test', result.exception.detail)
        self.assertNotIn('http', result.exception.detail)


if __name__ == '__main__':
    unittest.main()
