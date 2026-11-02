"""Onboarding y menú principal."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, CommandHandler

from services import SERVICE_LABELS


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    base = context.application.bot_data["settings"].web_form_base_url
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔑 Configurar {SERVICE_LABELS['real_debrid']}", callback_data="setup:real_debrid")],
        [InlineKeyboardButton(f"🔑 Configurar {SERVICE_LABELS['torbox']}", callback_data="setup:torbox")],
        [InlineKeyboardButton(f"🔑 Configurar {SERVICE_LABELS['alldebrid']}", callback_data="setup:alldebrid")],
        [InlineKeyboardButton("📅 ¿Cuándo caduca?", callback_data="query_menu")],
        [InlineKeyboardButton("🧰 Mis servicios", callback_data="manage_menu")],
        [InlineKeyboardButton("ℹ️ Cómo funciona", url=f"{base}/docs/USER_GUIDE.md"),
         InlineKeyboardButton("🔒 Privacidad", url=f"{base}/docs/PRIVACY.md")],
    ])
    await update.effective_message.reply_text(
        "¡Hola! Soy DebridWatch. Te ayudo a consultar y vigilar la caducidad "
        "de tus cuentas de debrid. Elige una opción:", reply_markup=keyboard
    )


def register(application) -> None:
    application.add_handler(CommandHandler("start", start))
