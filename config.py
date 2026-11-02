"""Configuración y validación de variables de entorno."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from cryptography.fernet import Fernet
from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    telegram_bot_token: str
    fernet_key: bytes
    web_form_base_url: str
    web_form_port: int
    scheduler_hour_utc: int
    log_level: str
    database_path: Path


def load_settings() -> Settings:
    """Carga .env si existe y falla pronto ante una configuración insegura."""
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    key = os.getenv("FERNET_KEY", "").strip()
    base_url = os.getenv("WEB_FORM_BASE_URL", "").strip().rstrip("/")
    if not token:
        raise ValueError("Falta TELEGRAM_BOT_TOKEN en el entorno o en .env")
    if not key:
        raise ValueError("Falta FERNET_KEY en el entorno o en .env")
    try:
        fernet_key = key.encode("ascii")
        Fernet(fernet_key)
    except (ValueError, UnicodeEncodeError) as exc:
        raise ValueError("FERNET_KEY no es una clave Fernet válida") from exc
    parsed = urlparse(base_url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise ValueError("WEB_FORM_BASE_URL debe ser una URL absoluta (HTTPS en producción)")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("WEB_FORM_BASE_URL debe ser el origen del dominio, sin ruta, query ni fragmento")
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("El formulario solo puede usar HTTP en localhost; en producción usa HTTPS")
    try:
        port = int(os.getenv("WEB_FORM_PORT", "8085"))
        hour = int(os.getenv("SCHEDULER_HOUR_UTC", "8"))
    except ValueError as exc:
        raise ValueError("WEB_FORM_PORT y SCHEDULER_HOUR_UTC deben ser números") from exc
    if not 1 <= port <= 65535:
        raise ValueError("WEB_FORM_PORT debe estar entre 1 y 65535")
    if not 0 <= hour <= 23:
        raise ValueError("SCHEDULER_HOUR_UTC debe estar entre 0 y 23")
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError("LOG_LEVEL no es válido")
    db_path = Path(os.getenv("DATABASE_PATH", "./debrid_watch.sqlite3")).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return Settings(token, fernet_key, base_url, port, hour, log_level, db_path)
