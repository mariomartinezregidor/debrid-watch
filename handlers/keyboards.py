"""Teclados inline de DebridWatch (fase de presentación, aún no conectados).

Los callback_data siguen el esquema ``pantalla:acción[:parámetro]``. Los
prefijos reservados son ``svc``, ``query``, ``services``, ``form``, ``back`` y
``nav``; el enrutador central se añadirá en ``callbacks.py``.
"""

from __future__ import annotations

from collections.abc import Sequence

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from services import SERVICE_LABELS


def main_menu_keyboard(docs_base_url: str) -> InlineKeyboardMarkup:
    """Menú raíz: selección de servicios, consultas, gestión y ayuda."""
    rows = [
        [InlineKeyboardButton(SERVICE_LABELS[name], callback_data=f"svc:{name}")]
        for name in ("torbox", "real_debrid", "alldebrid")
    ]
    rows.extend([
        [InlineKeyboardButton("📅 ¿Cuándo caduca?", callback_data="query:menu")],
        [InlineKeyboardButton("⚙️ Mis servicios", callback_data="services:list")],
        [
            InlineKeyboardButton("ℹ️ Cómo funciona", url=f"{docs_base_url.rstrip('/')}/docs/USER_GUIDE.md"),
            InlineKeyboardButton("🔒 Privacidad", url=f"{docs_base_url.rstrip('/')}/docs/PRIVACY.md"),
        ],
    ])
    return InlineKeyboardMarkup(rows)


def service_detail_keyboard(service_name: str, configured: bool,
                            back_data: str = "back:menu",
                            origin: str = "menu") -> InlineKeyboardMarkup:
    """Acciones para un servicio; eliminar siempre conduce primero a confirmar."""
    rows: list[list[InlineKeyboardButton]] = []
    suffix = ":from_services" if origin == "services" else ""
    if configured:
        query_origin = "from_svc_services" if origin == "services" else "from_svc"
        rows.extend([
            [InlineKeyboardButton("📅 ¿Cuándo caduca?", callback_data=f"query:{service_name}:{query_origin}")],
            [InlineKeyboardButton("🔄 Actualizar API Key", callback_data=f"svc:{service_name}:update{suffix}")],
            [InlineKeyboardButton("🗑️ Eliminar API Key", callback_data=f"svc:{service_name}:delete_confirm{suffix}")],
        ])
    else:
        rows.append([InlineKeyboardButton("➕ Añadir API Key", callback_data=f"svc:{service_name}:add{suffix}")])
    rows.extend([
        [InlineKeyboardButton("🔙 Volver", callback_data=back_data)],
        [InlineKeyboardButton("🏠 Menú principal", callback_data="back:menu")],
    ])
    return InlineKeyboardMarkup(rows)


def query_menu_keyboard(service_names: Sequence[str],
                        back_data: str = "back:menu") -> InlineKeyboardMarkup:
    """Una opción por servicio configurado, consulta global y navegación."""
    rows = [
        [InlineKeyboardButton(SERVICE_LABELS[name], callback_data=f"query:{name}")]
        for name in service_names if name in SERVICE_LABELS
    ]
    if rows:
        rows.append([InlineKeyboardButton("📋 Ver todos", callback_data="query:all")])
    rows.extend([
        [InlineKeyboardButton("🔙 Volver", callback_data=back_data)],
        [InlineKeyboardButton("🏠 Menú principal", callback_data="back:menu")],
    ])
    return InlineKeyboardMarkup(rows)


def services_list_keyboard(service_names: Sequence[str]) -> InlineKeyboardMarkup:
    """Lista de servicios configurados, cada uno abre su detalle."""
    rows = [
        [InlineKeyboardButton(SERVICE_LABELS[name], callback_data=f"svc:{name}:from_services")]
        for name in service_names if name in SERVICE_LABELS
    ]
    rows.extend([
        [InlineKeyboardButton("🔙 Volver", callback_data="back:menu")],
        [InlineKeyboardButton("🏠 Menú principal", callback_data="back:menu")],
    ])
    return InlineKeyboardMarkup(rows)


def delete_confirmation_keyboard(service_name: str, origin: str = "menu") -> InlineKeyboardMarkup:
    """La única pantalla que ofrece una acción destructiva confirmable."""
    suffix = ":from_services" if origin == "services" else ""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Sí, eliminar", callback_data=f"svc:{service_name}:delete{suffix}")],
        [InlineKeyboardButton("❌ Cancelar", callback_data=f"back:svc:{service_name}{suffix}")],
        [InlineKeyboardButton("🏠 Menú principal", callback_data="back:menu")],
    ])


def form_waiting_keyboard(service_name: str, form_url: str,
                          back_data: str | None = None,
                          origin: str = "menu") -> InlineKeyboardMarkup:
    """Pantalla de espera: abrir/reemitir el formulario o comprobar el alta."""
    suffix = ":from_services" if origin == "services" else ""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Abrir formulario seguro", url=form_url)],
        [InlineKeyboardButton("🔄 Ya la he guardado", callback_data=f"form:check:{service_name}{suffix}")],
        [InlineKeyboardButton("🔗 Reenviar enlace", callback_data=f"form:resend:{service_name}{suffix}")],
        [InlineKeyboardButton("🔙 Volver", callback_data=back_data or f"svc:{service_name}")],
        [InlineKeyboardButton("❌ Cancelar", callback_data="nav:cancel")],
        [InlineKeyboardButton("🏠 Menú principal", callback_data="back:menu")],
    ])


def query_result_keyboard(back_data: str = "back:query:menu") -> InlineKeyboardMarkup:
    """Navegación desde el resultado de una consulta manual."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Volver", callback_data=back_data)],
        [InlineKeyboardButton("🏠 Menú principal", callback_data="back:menu")],
    ])
