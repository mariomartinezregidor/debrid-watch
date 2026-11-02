"""Textos de las pantallas de navegación de DebridWatch.

Estas funciones son puras: reciben datos preparados por los handlers y no
acceden a Telegram, SQLite ni a los proveedores.
"""

from __future__ import annotations

from datetime import datetime
from collections.abc import Sequence

from handlers.common import format_date
from services import SERVICE_LABELS


def main_menu_text() -> str:
    return "¡Hola! Soy DebridWatch. Consulta y vigila la caducidad de tus cuentas. Elige una opción:"


def service_detail_text(service_name: str, configured: bool,
                        expiration_date: datetime | None = None) -> str:
    label = SERVICE_LABELS[service_name]
    if not configured:
        return f"{label}\n\nEste servicio todavía no está configurado."
    return f"{label}\n\nAPI Key configurada.\nCaducidad: {format_date(expiration_date)}"


def query_menu_text(service_names: Sequence[str]) -> str:
    if not service_names:
        return "No tienes servicios configurados. Añade una API Key para consultar la caducidad."
    return "¿Qué servicio quieres consultar? También puedes verlos todos:"


def services_list_text(services: Sequence[dict]) -> str:
    if not services:
        return "Todavía no tienes servicios configurados. Elige un servicio en el menú principal para añadirlo."
    lines = ["Tus servicios configurados. Elige uno para ver sus opciones:"]
    for item in services:
        name = item["service_name"]
        lines.append(f"• {SERVICE_LABELS[name]} — caducidad: {format_date(item.get('expiration_date'))}")
    return "\n".join(lines)


def delete_confirmation_text(service_name: str) -> str:
    return f"¿Seguro que quieres eliminar tu API Key de {SERVICE_LABELS[service_name]}? Dejarás de recibir avisos."


def form_waiting_text(service_name: str) -> str:
    return (
        f"Para configurar {SERVICE_LABELS[service_name]}, te he enviado un enlace. "
        "Ábrelo, introduce tu API Key en el formulario seguro y pulsa Guardar. "
        "El enlace caduca en 10 min."
    )


def form_saved_text(service_name: str, configured: bool) -> str:
    if configured:
        return f"✅ La API Key de {SERVICE_LABELS[service_name]} ya está guardada y validada."
    return "Aún no veo una API Key guardada. Abre el formulario y pulsa Guardar; puedes reenviar el enlace si caducó."


def query_result_text(text: str) -> str:
    return text


def query_all_text(rows: Sequence[str]) -> str:
    return "📋 Resumen de caducidad\n\nServicio | Caducidad (UTC) | Restantes\n" + "\n".join(rows)
