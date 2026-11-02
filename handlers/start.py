"""Onboarding y menú principal."""

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from handlers.keyboards import main_menu_keyboard
from handlers.screens import main_menu_text


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    base = context.application.bot_data["settings"].web_form_base_url
    await update.effective_message.reply_text(
        main_menu_text(), reply_markup=main_menu_keyboard(base)
    )


def register(application) -> None:
    application.add_handler(CommandHandler("start", start))
