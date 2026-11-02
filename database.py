"""Acceso asíncrono a SQLite. Todas las operaciones están aisladas por usuario."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiosqlite


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def dt_to_db(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value else None


def dt_from_db(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    async def initialize(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA foreign_keys=ON")
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS users_services (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_user_id INTEGER NOT NULL,
                    service_name TEXT NOT NULL,
                    api_key_encrypted TEXT NOT NULL,
                    expiration_date TEXT,
                    last_checked_at TEXT,
                    last_notified_threshold TEXT,
                    auth_error_notified INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(telegram_user_id, service_name)
                );
                CREATE INDEX IF NOT EXISTS idx_users_services_user
                    ON users_services(telegram_user_id);
                CREATE TABLE IF NOT EXISTS key_tokens (
                    token_hash TEXT PRIMARY KEY,
                    telegram_user_id INTEGER NOT NULL,
                    service_name TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)
            # Migración compatible con instalaciones anteriores.
            columns = {row[1] for row in await (await db.execute("PRAGMA table_info(users_services)")).fetchall()}
            if "auth_error_notified" not in columns:
                await db.execute("ALTER TABLE users_services ADD COLUMN auth_error_notified INTEGER NOT NULL DEFAULT 0")
            await db.commit()

    @staticmethod
    def _row(row: aiosqlite.Row | tuple[Any, ...]) -> dict[str, Any]:
        names = ["id", "telegram_user_id", "service_name", "api_key_encrypted", "expiration_date",
                 "last_checked_at", "last_notified_threshold", "auth_error_notified", "created_at", "updated_at"]
        result = dict(zip(names, row))
        result["expiration_date"] = dt_from_db(result["expiration_date"])
        result["last_checked_at"] = dt_from_db(result["last_checked_at"])
        return result

    async def list_services(self, user_id: int) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            rows = await (await db.execute(
                "SELECT id, telegram_user_id, service_name, api_key_encrypted, expiration_date, last_checked_at, "
                "last_notified_threshold, auth_error_notified, created_at, updated_at "
                "FROM users_services WHERE telegram_user_id=? ORDER BY service_name", (user_id,)
            )).fetchall()
        return [self._row(row) for row in rows]

    async def get_service(self, user_id: int, service_name: str) -> dict[str, Any] | None:
        services = await self.list_services(user_id)
        return next((item for item in services if item["service_name"] == service_name), None)

    async def issue_token(self, user_id: int, service_name: str) -> tuple[str, datetime]:
        token = secrets.token_urlsafe(32)
        expires = utcnow() + timedelta(minutes=10)
        digest = hashlib.sha256(token.encode()).hexdigest()
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM key_tokens WHERE expires_at < ?", (dt_to_db(utcnow()),))
            # Solo mantener vigente el último enlace generado para ese servicio.
            await db.execute("DELETE FROM key_tokens WHERE telegram_user_id=? AND service_name=?",
                             (user_id, service_name))
            await db.execute("INSERT INTO key_tokens VALUES (?, ?, ?, ?, ?)",
                             (digest, user_id, service_name, dt_to_db(expires), dt_to_db(utcnow())))
            await db.commit()
        return token, expires

    async def save_key_from_token(self, token: str, service_name: str, encrypted_key: str,
                                  expiration: datetime) -> int | None:
        digest = hashlib.sha256(token.encode()).hexdigest()
        now = utcnow()
        async with aiosqlite.connect(self.path, timeout=10) as db:
            await db.execute("BEGIN IMMEDIATE")
            row = await (await db.execute(
                "SELECT telegram_user_id, service_name, expires_at FROM key_tokens WHERE token_hash=?", (digest,)
            )).fetchone()
            if not row or row[1] != service_name or (dt_from_db(row[2]) or now) <= now:
                await db.rollback()
                return None
            user_id = int(row[0])
            existing = await (await db.execute(
                "SELECT expiration_date FROM users_services WHERE telegram_user_id=? AND service_name=?",
                (user_id, service_name)
            )).fetchone()
            old_exp = dt_from_db(existing[0]) if existing else None
            # Fernet usa un nonce aleatorio: el ciphertext cambia aunque la clave
            # en claro sea idéntica. Solo considerar renovación una extensión real.
            renewed = old_exp is not None and expiration > old_exp
            await db.execute("""INSERT INTO users_services
                (telegram_user_id, service_name, api_key_encrypted, expiration_date, last_checked_at,
                 last_notified_threshold, auth_error_notified, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, NULL, 0, ?, ?)
                ON CONFLICT(telegram_user_id, service_name) DO UPDATE SET
                api_key_encrypted=excluded.api_key_encrypted,
                expiration_date=excluded.expiration_date,
                last_checked_at=excluded.last_checked_at,
                last_notified_threshold=CASE WHEN ? THEN NULL ELSE users_services.last_notified_threshold END,
                auth_error_notified=0, updated_at=excluded.updated_at""",
                (user_id, service_name, encrypted_key, dt_to_db(expiration), dt_to_db(now), dt_to_db(now), dt_to_db(now), int(renewed)))
            await db.execute("DELETE FROM key_tokens WHERE token_hash=?", (digest,))
            await db.commit()
        return user_id

    async def delete_service(self, user_id: int, service_name: str) -> bool:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM key_tokens WHERE telegram_user_id=? AND service_name=?", (user_id, service_name))
            cursor = await db.execute("DELETE FROM users_services WHERE telegram_user_id=? AND service_name=?",
                                      (user_id, service_name))
            await db.commit()
            return cursor.rowcount > 0

    async def update_check(self, user_id: int, service_name: str, expiration: datetime) -> bool:
        now = utcnow()
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute("""UPDATE users_services SET
                last_notified_threshold=CASE WHEN expiration_date IS NOT NULL AND expiration_date != ?
                    AND ? > expiration_date THEN NULL ELSE last_notified_threshold END,
                expiration_date=?, last_checked_at=?, updated_at=?
                WHERE telegram_user_id=? AND service_name=?""",
                (dt_to_db(expiration), dt_to_db(expiration), dt_to_db(expiration), dt_to_db(now), dt_to_db(now), user_id, service_name))
            await db.commit()
            return cursor.rowcount > 0

    async def set_notified_threshold(self, user_id: int, service_name: str, threshold: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE users_services SET last_notified_threshold=?, updated_at=? WHERE telegram_user_id=? AND service_name=?",
                             (threshold, dt_to_db(utcnow()), user_id, service_name))
            await db.commit()

    async def mark_auth_error_once(self, user_id: int, service_name: str) -> bool:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("BEGIN IMMEDIATE")
            row = await (await db.execute("SELECT auth_error_notified FROM users_services WHERE telegram_user_id=? AND service_name=?",
                                          (user_id, service_name))).fetchone()
            if not row or row[0]:
                await db.rollback()
                return False
            await db.execute("UPDATE users_services SET auth_error_notified=1, updated_at=? WHERE telegram_user_id=? AND service_name=?",
                             (dt_to_db(utcnow()), user_id, service_name))
            await db.commit()
            return True
