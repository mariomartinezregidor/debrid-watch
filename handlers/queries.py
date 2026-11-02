"""Consultas manuales de caducidad."""

import logging

from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from crypto import KeyCipher
from handlers.common import days_remaining, format_date, service_keyboard
from services import AuthenticationError, ProviderError, SERVICE_LABELS

logger = logging.getLogger(__name__)


async def caducidad(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = await context.application.bot_data["db"].list_services(update.effective_user.id)
    if not services:
        await update.effective_message.reply_text("No tienes servicios configurados. Usa /start para añadir uno.")
        return
    await update.effective_message.reply_text("Elige un servicio o consulta todos:", reply_markup=service_keyboard("query", services))


async def _query_one(user_id: int, service_name: str, context: ContextTypes.DEFAULT_TYPE,
                     table_row: bool = False) -> str:
    db = context.application.bot_data["db"]
    item = await db.get_service(user_id, service_name)
    if not item:
        return f"{SERVICE_LABELS[service_name]} | Sin configurar | —" if table_row else f"No tienes {SERVICE_LABELS[service_name]} configurado."
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
                user_id, f"⚠️ La API Key de {SERVICE_LABELS[service_name]} ya no es válida. "
                "Actualízala desde /mis_servicios."
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


async def query_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, _, service_name = (query.data or "").partition(":")
    user_id = query.from_user.id
    if service_name == "all":
        services = await context.application.bot_data["db"].list_services(user_id)
        if not services:
            await query.edit_message_text("No tienes servicios configurados.")
            return
        # Consulta paralela: cada proveedor conserva su propio límite de 1 req/s.
        import asyncio
        results = await asyncio.gather(*[
            _query_one(user_id, item["service_name"], context, table_row=True) for item in services
        ])
        await query.edit_message_text(
            "📋 Resumen de caducidad\n\nServicio | Caducidad (UTC) | Restantes\n" + "\n".join(results)
        )
    elif service_name in SERVICE_LABELS:
        await query.edit_message_text("Consultando el servicio…")
        text = await _query_one(user_id, service_name, context)
        await query.edit_message_text(text)


def register(application) -> None:
    application.add_handler(CommandHandler("caducidad", caducidad))
    application.add_handler(CallbackQueryHandler(query_callback, pattern=r"^query:"))
