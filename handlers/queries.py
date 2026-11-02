"""Comando de consulta y lógica compartida de caducidad."""

import logging

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from crypto import KeyCipher
from handlers.common import days_remaining, format_date
from handlers.keyboards import query_menu_keyboard
from handlers.screens import query_menu_text
from services import AuthenticationError, ProviderError, SERVICE_LABELS

logger = logging.getLogger(__name__)


async def caducidad(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = await context.application.bot_data["db"].list_services(update.effective_user.id)
    names = [item["service_name"] for item in services]
    # Los comandos crean la pantalla inicial; los botones la navegan editándola.
    await update.effective_message.reply_text(
        query_menu_text(names), reply_markup=query_menu_keyboard(names)
    )


async def _query_one(user_id: int, service_name: str, context: ContextTypes.DEFAULT_TYPE,
                     table_row: bool = False) -> str:
    """Consulta un servicio aislando errores y conserva el aviso de key revocada."""
    db = context.application.bot_data["db"]
    item = await db.get_service(user_id, service_name)
    if not item:
        if table_row:
            return f"{SERVICE_LABELS[service_name]} | Sin configurar | —"
        return f"No tienes {SERVICE_LABELS[service_name]} configurado."
    cipher: KeyCipher = context.application.bot_data["cipher"]
    try:
        expiration = await context.application.bot_data["providers"][service_name].get_expiration(
            cipher.decrypt(item["api_key_encrypted"])
        )
        await db.update_check(user_id, service_name, expiration)
        days = days_remaining(expiration)
        state = "caducado" if days <= 0 else f"quedan {days} día(s)"
        if table_row:
            return f"{SERVICE_LABELS[service_name]} | {format_date(expiration)} | {days} día(s)"
        return f"{SERVICE_LABELS[service_name]}: {format_date(expiration)} ({state})."
    except AuthenticationError:
        if await db.mark_auth_error_once(user_id, service_name):
            await context.bot.send_message(
                user_id,
                f"⚠️ La API Key de {SERVICE_LABELS[service_name]} ya no es válida. "
                "Actualízala desde /mis_servicios.",
            )
        if table_row:
            return f"{SERVICE_LABELS[service_name]} | Error | API Key inválida"
        return f"No se pudo consultar {SERVICE_LABELS[service_name]}: la API Key fue rechazada. Revisa /mis_servicios."
    except ProviderError as exc:
        logger.warning("Consulta manual fallida: servicio=%s tipo=%s", service_name, type(exc).__name__)
        if table_row:
            return f"{SERVICE_LABELS[service_name]} | Error | No disponible"
        return f"No se pudo consultar {SERVICE_LABELS[service_name]} ahora. Inténtalo más tarde."
    except Exception:
        logger.exception("Error inesperado consultando servicio: servicio=%s", service_name)
        if table_row:
            return f"{SERVICE_LABELS[service_name]} | Error | No disponible"
        return f"Ocurrió un error consultando {SERVICE_LABELS[service_name]}. Inténtalo más tarde."


def register(application) -> None:
    application.add_handler(CommandHandler("caducidad", caducidad))
