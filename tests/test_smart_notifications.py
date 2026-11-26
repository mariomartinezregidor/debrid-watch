"""Pruebas de avisos inteligentes, enlaces de renovación y anti rate-limit."""

import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import formatdate
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
from cryptography.fernet import Fernet

from crypto import KeyCipher
from database import Database, dt_to_db
from notifications import build_alert, needs_refresh
from renewal import renewal_keyboard, renewal_url
from scheduler_jobs import daily_expiration_check
from services import RateLimitedError
from services.base import DebridService


class CountingService(DebridService):
    name = "counting"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.calls = 0

    async def get_expiration(self, api_key: str) -> datetime:
        self.calls += 1
        await asyncio.sleep(0.01)
        return datetime.now(timezone.utc) + timedelta(days=5)


class DummyService(DebridService):
    name = "dummy"

    async def get_expiration(self, api_key: str) -> datetime:
        await self._get_json("https://example.test/user", api_key)
        return datetime(2030, 1, 1, tzinfo=timezone.utc)


class RenewalAndAlertTests(unittest.TestCase):
    def test_renewal_links_only_for_supported_providers(self):
        for name in ("torbox", "real_debrid", "alldebrid"):
            url = renewal_url(name)
            self.assertTrue(url and url.startswith("https://"), name)
            markup = renewal_keyboard(name)
            self.assertIsNotNone(markup)
            self.assertEqual(url, markup.inline_keyboard[0][0].url)
        self.assertIsNone(renewal_url("putio"))
        self.assertIsNone(renewal_keyboard("putio"))

    def test_alerts_respect_thresholds_and_include_renewal_link(self):
        now = datetime.now(timezone.utc)
        for days, expected in ((20, None), (14, "14"), (7, "7"), (3, "3"), (1, "1"), (-1, "expired")):
            with self.subTest(days=days):
                # Un segundo menos evita que el redondeo hacia arriba suba el día.
                alert = build_alert("torbox", now + timedelta(days=days) - timedelta(seconds=1))
                if expected is None:
                    self.assertIsNone(alert)
                else:
                    self.assertEqual(expected, alert.threshold)
                    self.assertIn("https://torbox.app/subscription", alert.text)

    def test_refresh_window_depends_on_urgency(self):
        now = datetime.now(timezone.utc)
        checked = now - timedelta(hours=3)
        far = now + timedelta(days=40)
        near = now + timedelta(days=2)
        self.assertFalse(needs_refresh(checked, far, now))
        self.assertTrue(needs_refresh(checked, near, now))
        self.assertTrue(needs_refresh(None, far, now))


class ApiOptimizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_reads_share_one_request_and_respect_ttl(self):
        service = CountingService(cache_ttl=60)
        try:
            results = await asyncio.gather(*[service.get_cached_expiration("secret") for _ in range(6)])
            self.assertEqual(1, service.calls)
            self.assertEqual(1, len({item for item in results}))
            self.assertEqual(1, (await service.get_cached_expiration("secret")) and service.calls)
            self.assertEqual(2, (await service.get_cached_expiration("secret", force=True)) and service.calls)
        finally:
            await service.close()

    async def test_429_sets_cooldown_and_retry_after_is_honored(self):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(429, headers={"Retry-After": "60"})
            return httpx.Response(200, json={"ok": True})

        service = DummyService(min_interval=0.2)
        await service._client.aclose()
        service._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            with self.assertRaises(RateLimitedError) as first:
                await service.get_expiration("secret")
            self.assertAlmostEqual(60, first.exception.retry_after, delta=1)
            with self.assertRaises(RateLimitedError):
                await service.get_expiration("secret")
            self.assertEqual(1, len(calls), "durante el enfriamiento no debe haber llamadas")
            self.assertEqual(60.0, DebridService.parse_retry_after_seconds("60"))
            self.assertAlmostEqual(
                120.0,
                DebridService.parse_retry_after_seconds(
                    formatdate((datetime.now(timezone.utc) + timedelta(seconds=120)).timestamp(), usegmt=True)
                ),
                delta=2,
            )
        finally:
            await service.close()

    async def test_cache_is_isolated_per_credential(self):
        service = CountingService(cache_ttl=60)
        try:
            await service.get_cached_expiration("key-A")
            await service.get_cached_expiration("key-B")
            self.assertEqual(2, service.calls)
            await service.get_cached_expiration("key-A")
            self.assertEqual(2, service.calls)
        finally:
            await service.close()


class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tempdir.name) / "alerts.sqlite3")
        await self.db.initialize()
        self.cipher = KeyCipher(Fernet.generate_key())
        self.bot = AsyncMock()
        self.provider = AsyncMock()
        self.settings = SimpleNamespace(
            alert_thresholds_days=(14, 7, 3, 1), check_freshness_hours=12,
            urgent_check_hours=2, api_cache_ttl_seconds=900,
        )
        self.app = SimpleNamespace(bot_data={
            "db": self.db, "cipher": self.cipher, "bot": self.bot,
            "providers": {"torbox": self.provider}, "settings": self.settings,
        }, bot=self.bot)
        self.context = SimpleNamespace(application=self.app)

    async def asyncTearDown(self):
        self.tempdir.cleanup()

    async def _add_service(self, expiration: datetime) -> None:
        token, _ = await self.db.issue_token(4242, "torbox")
        await self.db.save_key_from_token(token, "torbox", self.cipher.encrypt("secret"), expiration)

    async def test_alert_is_sent_once_with_renewal_button_and_threshold_recorded(self):
        expiration = datetime.now(timezone.utc) + timedelta(days=3) - timedelta(seconds=1)
        await self._add_service(expiration)
        self.provider.get_cached_expiration.return_value = expiration

        await daily_expiration_check(self.context)
        self.bot.send_message.assert_awaited_once()
        kwargs = self.bot.send_message.await_args.kwargs
        self.assertIsNotNone(kwargs["reply_markup"])
        self.assertEqual("https://torbox.app/subscription",
                         kwargs["reply_markup"].inline_keyboard[0][0].url)
        self.assertEqual("3", (await self.db.get_service(4242, "torbox"))["last_notified_threshold"])

        await daily_expiration_check(self.context)
        self.assertEqual(1, self.bot.send_message.await_count, "el aviso no debe repetirse")

    async def test_recent_record_avoids_api_call_and_renewal_resets_threshold(self):
        expiration = datetime.now(timezone.utc) + timedelta(days=3, hours=1)
        await self._add_service(expiration)
        await daily_expiration_check(self.context)
        self.provider.get_cached_expiration.assert_not_awaited()

        renewed = expiration + timedelta(days=30)
        self.provider.get_cached_expiration.return_value = renewed
        async with __import__("aiosqlite").connect(self.db.path) as connection:
            await connection.execute(
                "UPDATE users_services SET last_checked_at=? WHERE telegram_user_id=4242",
                (dt_to_db(datetime.now(timezone.utc) - timedelta(hours=5)),),
            )
            await connection.commit()
        await daily_expiration_check(self.context)
        self.provider.get_cached_expiration.assert_awaited_once()
        self.assertIsNone((await self.db.get_service(4242, "torbox"))["last_notified_threshold"])


if __name__ == "__main__":
    unittest.main()
