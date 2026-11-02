"""Helpers compartidos por los handlers."""

from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from services import SERVICE_LABELS


def service_keyboard(action: str, services: list[dict] | None = None) -> InlineKeyboardMarkup:
    names = list(SERVICE_LABELS)
    if services is not None:
        configured = {item["service_name"] for item in services}
        names = [name for name in names if name in configured]
    rows = [[InlineKeyboardButton(SERVICE_LABELS[name], callback_data=f"{action}:{name}")] for name in names]
    if action == "query" and names:
        rows.append([InlineKeyboardButton("Ver todos", callback_data="query:all")])
    return InlineKeyboardMarkup(rows)


def format_date(value: datetime | None) -> str:
    if value is None:
        return "No disponible"
    return value.astimezone(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")


def days_remaining(value: datetime) -> int:
    seconds = (value - datetime.now(timezone.utc)).total_seconds()
    # Redondeo hacia arriba: en el punto de comprobación diario se conserva
    # el umbral durante sus últimas 24 horas completas.
    import math
    return math.ceil(seconds / 86400)
