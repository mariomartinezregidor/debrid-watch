"""Comprobación inteligente de caducidades, aislada por usuario.

Reduce llamadas a la API de tres formas: reutiliza la fecha guardada si es
reciente, comparte respuestas en caché entre comandos y job, y respeta el
``Retry-After`` de un HTTP 429. Los avisos incluyen el enlace de renovación
cuando el proveedor ofrece uno oficial.
"""

from __future__ import annotations

import logging
from datetime import time, timezone

import aiosqlite
from telegram.ext import Application, ContextTypes

from crypto import KeyCipher
from database import dt_from_db, utcnow
from notifications import build_alert, needs_refresh
from renewal import renewal_keyboard
from services import AuthenticationError, ProviderError, RateLimitedError, SERVICE_LABELS

logger = logging.getLogger(__name__)


async def _resolve_expiration(row: tuple, *, application: Application,
                              settings, cipher: KeyCipher) -> tuple:
    """Devuelve (caducidad, consulta_refrescada) priorizando datos recientes."""
    _user_id, service_name, encrypted, stored_expiration, stored_check, _threshold = row
    expiration = dt_from_db(stored_expiration)
    last_check = dt_from_db(stored_check)
    if not needs_refresh(last_check, expiration, utcnow(),
                         freshness_hours=settings.check_freshness_hours,
                         urgent_hours=settings.urgent_check_hours):
        return expiration, False
    api_key = cipher.decrypt(encrypted)
    expiration = await application.bot_data["providers"][service_name].get_cached_expiration(
        api_key, ttl=settings.api_cache_ttl_seconds
    )
    return expiration, True


async def daily_expiration_check(context: ContextTypes.DEFAULT_TYPE) -> None:
    app = context.application
    db = app.bot_data["db"]
    cipher: KeyCipher = app.bot_data["cipher"]
    settings = app.bot_data["settings"]
    # Se recorre la tabla completa, pero cada error queda confinado a su fila.
    async with aiosqlite.connect(db.path) as connection:
        rows = await (await connection.execute("""SELECT telegram_user_id, service_name, api_key_encrypted,
            expiration_date, last_checked_at, last_notified_threshold FROM users_services""")).fetchall()

    for row in rows:
        user_id, service_name, _encrypted, _exp, _checked, previous_threshold = row
        try:
            expiration, refreshed = await _resolve_expiration(
                row, application=app, settings=settings, cipher=cipher
            )
            if refreshed:
                await db.update_check(user_id, service_name, expiration)
            alert = build_alert(service_name, expiration, settings.alert_thresholds_days)
            if alert is None:
                continue
            # Si la consulta descubrió una renovación (fecha posterior), el
            # almacenamiento ya ha limpiado el umbral anterior.
            current = await db.get_service(user_id, service_name)
            last = current["last_notified_threshold"] if current else previous_threshold
            if last == alert.threshold:
                continue
            await app.bot.send_message(
                int(user_id), alert.text, reply_markup=renewal_keyboard(service_name)
            )
            await db.set_notified_threshold(user_id, service_name, alert.threshold)
        except RateLimitedError as exc:
            # Un 429 no es un error de credencial: se omite la fila y se espera
            # al enfriamiento calculado por el cliente del proveedor.
            logger.warning("Proveedor con rate-limit: servicio=%s retry_after=%s",
                           service_name, getattr(exc, "retry_after", None))
        except AuthenticationError:
            if await db.mark_auth_error_once(user_id, service_name):
                try:
                    await app.bot.send_message(
                        int(user_id), f"⚠️ La API Key de {SERVICE_LABELS[service_name]} ya no es válida. "
                        "Actualízala desde /mis_servicios."
                    )
                except Exception:
                    logger.exception("No se pudo enviar aviso de credencial: servicio=%s", service_name)
        except ProviderError as exc:
            logger.warning("Comprobación fallida: servicio=%s tipo=%s", service_name, type(exc).__name__)
        except Exception:
            logger.exception("Error aislado en comprobación: servicio=%s", service_name)


def configure_scheduler(application: Application, hour_utc: int,
                        extra_hours_utc: tuple[int, ...] = ()) -> None:
    """Registra la comprobación principal y las adicionales en UTC."""
    from datetime import time as time_of_day
    for hour in (hour_utc, *extra_hours_utc):
        name = "daily-expiration-check" if hour == hour_utc else f"daily-expiration-check-{hour:02d}"
        application.job_queue.run_daily(
            daily_expiration_check,
            time=time_of_day(hour=hour, minute=0, tzinfo=timezone.utc),
            name=name, job_kwargs={"max_instances": 1, "coalesce": True},
        )
