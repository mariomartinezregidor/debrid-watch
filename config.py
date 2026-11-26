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
    alert_thresholds_days: tuple[int, ...]
    api_cache_ttl_seconds: int
    api_min_interval_seconds: float
    check_freshness_hours: int
    urgent_check_hours: int
    extra_check_hours_utc: tuple[int, ...]


def _int_list(name: str, default: str, *, minimum: int, maximum: int,
              allow_empty: bool = False) -> tuple[int, ...]:
    """Lee una lista de enteros separada por comas y valida su rango."""
    raw = os.getenv(name, default).strip()
    if not raw and allow_empty:
        return ()
    try:
        values = tuple(int(part.strip()) for part in raw.split(",") if part.strip())
    except ValueError as exc:
        raise ValueError(f"{name} debe ser una lista de números separada por comas") from exc
    if not values or any(not minimum <= value <= maximum for value in values):
        raise ValueError(f"{name} debe contener valores entre {minimum} y {maximum}")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} no puede repetir valores")
    return values


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
    thresholds = _int_list("ALERT_THRESHOLDS_DAYS", "14,7,3,1", minimum=1, maximum=365)
    extra_hours = _int_list("EXTRA_CHECK_HOURS_UTC", "", minimum=0, maximum=23, allow_empty=True)
    if hour in extra_hours:
        raise ValueError("EXTRA_CHECK_HOURS_UTC no puede repetir SCHEDULER_HOUR_UTC")
    try:
        cache_ttl = int(os.getenv("API_CACHE_TTL_SECONDS", "900"))
        min_interval = float(os.getenv("API_MIN_INTERVAL_SECONDS", "1.0"))
        freshness = int(os.getenv("CHECK_FRESHNESS_HOURS", "16"))
        urgent = int(os.getenv("URGENT_CHECK_HOURS", "2"))
    except ValueError as exc:
        raise ValueError("Los parámetros de caché y comprobación deben ser números") from exc
    if not 0 <= cache_ttl <= 86400:
        raise ValueError("API_CACHE_TTL_SECONDS debe estar entre 0 y 86400")
    if not 0.2 <= min_interval <= 60:
        raise ValueError("API_MIN_INTERVAL_SECONDS debe estar entre 0.2 y 60")
    if not 0 <= freshness <= 168:
        raise ValueError("CHECK_FRESHNESS_HOURS debe estar entre 0 y 168")
    if not 0 <= urgent <= 72:
        raise ValueError("URGENT_CHECK_HOURS debe estar entre 0 y 72")
    db_path = Path(os.getenv("DATABASE_PATH", "./debrid_watch.sqlite3")).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return Settings(
        telegram_bot_token=token, fernet_key=fernet_key, web_form_base_url=base_url,
        web_form_port=port, scheduler_hour_utc=hour, log_level=log_level,
        database_path=db_path, alert_thresholds_days=thresholds,
        api_cache_ttl_seconds=cache_ttl, api_min_interval_seconds=min_interval,
        check_freshness_hours=freshness, urgent_check_hours=urgent,
        extra_check_hours_utc=extra_hours,
    )
