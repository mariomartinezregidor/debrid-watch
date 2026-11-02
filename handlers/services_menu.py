"""Configuración y gestión privada de las credenciales."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from handlers.common import format_date
from services import SERVICE_LABELS


async def _setup_link(query, context: ContextTypes.DEFAULT_TYPE, service_name: str) -> None:
    db = context.application.bot_data["db"]
    settings = context.application.bot_data["settings"]
    token, _expires = await db.issue_token(query.from_user.id, service_name)
    url = f"{settings.web_form_base_url}/key/{token}"
    await query.edit_message_text(
        f"Para configurar {SERVICE_LABELS[service_name]}, abre el formulario seguro. "
        "La clave no se enviará al chat. El enlace es de un solo uso y caduca en 10 minutos.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Abrir formulario seguro 🔒", url=url)]]),
    )


async def manage_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_services(update, context, edit=False)


async def show_services(update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool = True) -> None:
    user_id = update.effective_user.id
    await _show_services(user_id, context, update.callback_query if edit else None, update.effective_message)


async def _show_services(user_id: int, context: ContextTypes.DEFAULT_TYPE, query=None, message=None) -> None:
    services = await context.application.bot_data["db"].list_services(user_id)
    if not services:
        text = "Todavía no tienes servicios configurados. Usa /start para añadir uno."
        if query:
            await query.edit_message_text(text)
        else:
            await message.reply_text(text)
        return
    rows = []
    lines = ["Estos son tus servicios configurados:"]
    for item in services:
        name = item["service_name"]
        lines.append(f"• {SERVICE_LABELS[name]} — caducidad: {format_date(item['expiration_date'])}")
        rows.append([
            InlineKeyboardButton(f"Actualizar {SERVICE_LABELS[name]}", callback_data=f"service:update:{name}"),
            InlineKeyboardButton("Borrar", callback_data=f"service:delete:{name}"),
        ])
    markup = InlineKeyboardMarkup(rows)
    if query:
        await query.edit_message_text("\n".join(lines), reply_markup=markup)
    else:
        await message.reply_text("\n".join(lines), reply_markup=markup)


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    action, _, service_name = (query.data or "").partition(":")
    if action == "setup_menu":
        from handlers.common import service_keyboard
        await query.edit_message_text("Elige el servicio que quieres configurar:", reply_markup=service_keyboard("setup"))
    elif action == "query_menu":
        from handlers.common import service_keyboard
        user_services = await context.application.bot_data["db"].list_services(query.from_user.id)
        if not user_services:
            await query.edit_message_text("Aún no tienes servicios configurados. Usa /start para añadir uno.")
        else:
            await query.edit_message_text("¿Qué servicio quieres consultar?", reply_markup=service_keyboard("query", user_services))
    elif action == "manage_menu":
        await _show_services(query.from_user.id, context, query=query)
    elif action == "setup" and service_name in SERVICE_LABELS:
        await _setup_link(query, context, service_name)
    elif action == "service":
        # Formato service:update:<name> / service:delete:<name>
        parts = (query.data or "").split(":")
        if len(parts) == 3 and parts[2] in SERVICE_LABELS:
            verb, name = parts[1], parts[2]
            if verb == "update":
                await _setup_link(query, context, name)
            elif verb == "delete":
                await query.edit_message_text(
                    f"¿Borrar la credencial de {SERVICE_LABELS[name]}?",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("Sí, borrar", callback_data=f"delete_confirm:{name}"),
                        InlineKeyboardButton("Cancelar", callback_data="manage_menu"),
                    ]]),
                )
    elif action == "delete_confirm" and service_name in SERVICE_LABELS:
        removed = await context.application.bot_data["db"].delete_service(query.from_user.id, service_name)
        await query.edit_message_text("Servicio eliminado." if removed else "Ese servicio ya no estaba configurado.")


def register(application) -> None:
    application.add_handler(CommandHandler("mis_servicios", manage_command))
    application.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^(setup_menu|query_menu|manage_menu|setup:|service:|delete_confirm:).*"))
