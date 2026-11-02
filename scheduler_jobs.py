"""Comprobación periódica y avisos de caducidad, aislados por usuario."""

from __future__ import annotations

import logging
from datetime import timezone

import aiosqlite
from telegram.ext import Application, ContextTypes

from crypto import KeyCipher
from handlers.common import days_remaining, format_date
from services import AuthenticationError, ProviderError, SERVICE_LABELS

logger = logging.getLogger(__name__)


async def daily_expiration_check(context: ContextTypes.DEFAULT_TYPE) -> None:
    app = context.application
    db = app.bot_data["db"]
    cipher: KeyCipher = app.bot_data["cipher"]
    # Se recorre la tabla completa, pero cada error queda confinado a su fila.
    async with aiosqlite.connect(db.path) as connection:
        rows = await (await connection.execute("""SELECT telegram_user_id, service_name, api_key_encrypted,
            last_notified_threshold FROM users_services""")).fetchall()
    for user_id, service_name, encrypted, previous_threshold in rows:
        try:
            expiration = await app.bot_data["providers"][service_name].get_expiration(cipher.decrypt(encrypted))
            await db.update_check(user_id, service_name, expiration)
            remaining = days_remaining(expiration)
            if remaining <= 0:
                threshold, message = "expired", f"❌ Tu suscripción de {SERVICE_LABELS[service_name]} ha caducado"
            elif remaining <= 1:
                threshold, message = "1", f"⚠️ Tu suscripción de {SERVICE_LABELS[service_name]} caduca en 1 día ({format_date(expiration)})"
            elif remaining <= 3:
                threshold, message = "3", f"⚠️ Tu suscripción de {SERVICE_LABELS[service_name]} caduca en 3 días ({format_date(expiration)})"
            elif remaining <= 7:
                threshold, message = "7", f"⚠️ Tu suscripción de {SERVICE_LABELS[service_name]} caduca en 7 días ({format_date(expiration)})"
            else:
                continue
            # Si la consulta descubrió una renovación (fecha posterior), el
            # almacenamiento ya ha limpiado el umbral anterior.
            current = await db.get_service(user_id, service_name)
            last = current["last_notified_threshold"] if current else previous_threshold
            if last == threshold:
                continue
            await app.bot.send_message(int(user_id), message)
            await db.set_notified_threshold(user_id, service_name, threshold)
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


def configure_scheduler(application: Application, hour_utc: int) -> None:
    """Registra el job diario a la hora UTC configurada."""
    from datetime import time
    application.job_queue.run_daily(
        daily_expiration_check, time=time(hour=hour_utc, minute=0, tzinfo=timezone.utc),
        name="daily-expiration-check", job_kwargs={"max_instances": 1, "coalesce": True},
    )
