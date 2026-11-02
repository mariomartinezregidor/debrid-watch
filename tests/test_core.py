"""Pruebas de aislamiento, enlaces de un solo uso y formulario."""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
from cryptography.fernet import Fernet

from crypto import KeyCipher
from database import Database
from services import AuthenticationError
from services.base import DebridService
from web_form.app import create_web_app


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tempdir.name) / "test.sqlite3")
        await self.db.initialize()
        self.cipher = KeyCipher(Fernet.generate_key())

    async def asyncTearDown(self):
        self.tempdir.cleanup()

    async def test_tokens_are_single_use_and_isolated_by_user(self):
        expiration = datetime.now(timezone.utc) + timedelta(days=20)
        token_a, _ = await self.db.issue_token(101, "real_debrid")
        token_b, _ = await self.db.issue_token(202, "torbox")
        self.assertEqual(101, await self.db.save_key_from_token(
            token_a, "real_debrid", self.cipher.encrypt("secret-A"), expiration
        ))
        self.assertIsNone(await self.db.save_key_from_token(
            token_a, "real_debrid", self.cipher.encrypt("secret-again"), expiration
        ))
        self.assertEqual(202, await self.db.save_key_from_token(
            token_b, "torbox", self.cipher.encrypt("secret-B"), expiration
        ))
        a_services = await self.db.list_services(101)
        b_services = await self.db.list_services(202)
        self.assertEqual(["real_debrid"], [row["service_name"] for row in a_services])
        self.assertEqual(["torbox"], [row["service_name"] for row in b_services])
        self.assertEqual("secret-A", self.cipher.decrypt(a_services[0]["api_key_encrypted"]))
        self.assertNotEqual("secret-A", a_services[0]["api_key_encrypted"])

    async def test_user_cannot_save_token_for_another_service(self):
        token, _ = await self.db.issue_token(55, "torbox")
        self.assertIsNone(await self.db.save_key_from_token(
            token, "real_debrid", self.cipher.encrypt("secret"), datetime.now(timezone.utc)
        ))
        self.assertEqual([], await self.db.list_services(55))

    async def test_same_expiration_does_not_reset_notification_but_renewal_does(self):
        expiration = datetime.now(timezone.utc) + timedelta(days=4)
        token, _ = await self.db.issue_token(77, "torbox")
        await self.db.save_key_from_token(token, "torbox", self.cipher.encrypt("same-key"), expiration)
        await self.db.set_notified_threshold(77, "torbox", "3")

        token, _ = await self.db.issue_token(77, "torbox")
        await self.db.save_key_from_token(token, "torbox", self.cipher.encrypt("same-key"), expiration)
        self.assertEqual("3", (await self.db.get_service(77, "torbox"))["last_notified_threshold"])

        token, _ = await self.db.issue_token(77, "torbox")
        await self.db.save_key_from_token(
            token, "torbox", self.cipher.encrypt("same-key"), expiration + timedelta(days=30)
        )
        self.assertIsNone((await self.db.get_service(77, "torbox"))["last_notified_threshold"])


class ProviderParsingTests(unittest.TestCase):
    def test_unix_timestamp_and_naive_iso_are_normalized_to_utc(self):
        timestamp = 1_800_000_000
        self.assertEqual(datetime.fromtimestamp(timestamp, timezone.utc), DebridService.parse_datetime(timestamp))
        self.assertEqual(timezone.utc, DebridService.parse_datetime("2030-01-02T03:04:05").tzinfo)


class WebFormTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tempdir.name) / "web.sqlite3")
        await self.db.initialize()
        self.cipher = KeyCipher(Fernet.generate_key())
        self.expiration = datetime.now(timezone.utc) + timedelta(days=30)
        self.provider = AsyncMock()
        self.provider.get_expiration.return_value = self.expiration
        self.bot = AsyncMock()
        self.app = create_web_app()
        self.app.state.db = self.db
        self.app.state.cipher = self.cipher
        self.app.state.providers = {"real_debrid": self.provider}
        self.app.state.bot = self.bot
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="https://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        self.tempdir.cleanup()

    async def test_valid_key_is_encrypted_and_not_echoed(self):
        token, _ = await self.db.issue_token(876, "real_debrid")
        get_response = await self.client.get(f"/key/{token}")
        self.assertEqual(200, get_response.status_code)
        self.assertIn("no-store", get_response.headers["cache-control"])
        response = await self.client.post(f"/key/{token}", data={"api_key": "secret-from-form"})
        self.assertEqual(200, response.status_code)
        self.assertNotIn("secret-from-form", response.text)
        row = (await self.db.list_services(876))[0]
        self.assertEqual("secret-from-form", self.cipher.decrypt(row["api_key_encrypted"]))
        self.bot.send_message.assert_awaited_once()
        replay = await self.client.post(f"/key/{token}", data={"api_key": "another-secret"})
        self.assertEqual(410, replay.status_code)

    async def test_invalid_key_is_not_saved_and_link_can_be_retried(self):
        token, _ = await self.db.issue_token(888, "real_debrid")
        self.provider.get_expiration.side_effect = AuthenticationError("invalid")
        response = await self.client.post(f"/key/{token}", data={"api_key": "bad-secret"})
        self.assertEqual(400, response.status_code)
        self.assertEqual([], await self.db.list_services(888))
        self.assertIn("sigue disponible", response.text)


if __name__ == "__main__":
    unittest.main()
