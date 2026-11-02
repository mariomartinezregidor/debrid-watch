"""Pruebas de parseo/autenticación de los proveedores añadidos."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from services import AuthenticationError
from services.debridlink import DebridLinkService
from services.offcloud import OffcloudService
from services.premiumize import PremiumizeService
from services.putio import PutioService


class AddedProviderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.providers = [
            PremiumizeService(), DebridLinkService(), OffcloudService(), PutioService()
        ]

    async def asyncTearDown(self):
        for provider in self.providers:
            await provider.close()

    async def test_premiumize_parses_unix_expiration_and_free_account(self):
        service = self.providers[0]
        expires = 1_800_000_000
        service._get_json = AsyncMock(return_value={"status": "success", "premium_until": expires})
        self.assertEqual(datetime.fromtimestamp(expires, timezone.utc), await service.get_expiration("secret"))
        service._get_json = AsyncMock(return_value={"status": "success", "premium_until": None})
        now = datetime.now(timezone.utc)
        result = await service.get_expiration("secret")
        self.assertLess(abs((result - now).total_seconds()), 2)

    async def test_debridlink_converts_seconds_remaining_to_absolute_utc(self):
        service = self.providers[1]
        service._get_json = AsyncMock(return_value={"success": True, "value": {"premiumLeft": 3600}})
        before = datetime.now(timezone.utc)
        result = await service.get_expiration("secret")
        self.assertAlmostEqual(3600, (result - before).total_seconds(), delta=2)
        service._get_json = AsyncMock(return_value={"success": False, "error": "badToken"})
        with self.assertRaises(AuthenticationError):
            await service.get_expiration("secret")

    async def test_offcloud_uses_bearer_auth_and_reads_nested_expiry(self):
        service = self.providers[2]
        service._get_json = AsyncMock(return_value={
            "account": {"subscription": {"expirationDate": "2030-01-02T03:04:05Z"}}
        })
        result = await service.get_expiration("secret")
        self.assertEqual(datetime(2030, 1, 2, 3, 4, 5, tzinfo=timezone.utc), result)
        service._get_json.assert_awaited_once_with(service.endpoint, "secret")

    async def test_putio_uses_token_auth_and_parses_account_info(self):
        service = self.providers[3]
        service._get_json = AsyncMock(return_value={
            "info": {"expiration_date": "2031-02-03T04:05:06Z"}
        })
        result = await service.get_expiration("secret")
        self.assertEqual(datetime(2031, 2, 3, 4, 5, 6, tzinfo=timezone.utc), result)
        service._get_json.assert_awaited_once_with(
            service.endpoint, "secret", auth_scheme="Token"
        )

    async def test_putio_can_convert_days_remaining(self):
        service = self.providers[3]
        service._get_json = AsyncMock(return_value={"info": {"days_until_expiration": 2}})
        now = datetime.now(timezone.utc)
        result = await service.get_expiration("secret")
        self.assertAlmostEqual(2 * 86400, (result - now).total_seconds(), delta=2)


if __name__ == "__main__":
    unittest.main()
