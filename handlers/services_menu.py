"""Comando para abrir la lista de servicios configurados."""

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from handlers.keyboards import services_list_keyboard
from handlers.screens import services_list_text


async def manage_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = await context.application.bot_data["db"].list_services(update.effective_user.id)
    service_names = [item["service_name"] for item in services]
    # Un comando inicia una pantalla nueva; después, la navegación edita este mensaje.
    await update.effective_message.reply_text(
        services_list_text(services),
        reply_markup=services_list_keyboard(service_names),
    )


def register(application) -> None:
    application.add_handler(CommandHandler("mis_servicios", manage_command))
