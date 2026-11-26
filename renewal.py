"""Enlaces oficiales de renovación para los proveedores con avisos inteligentes.

Son páginas públicas de los proveedores: el bot nunca solicita datos de pago
ni guarda información de suscripción. Solo se usan para ofrecer al usuario un
acceso directo al lugar donde puede renovar su plan.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# URLs oficiales verificadas en noviembre de 2026. Si un proveedor cambia su
# página de pago, basta con actualizar este mapa.
RENEWAL_URLS: dict[str, str] = {
    "real_debrid": "https://real-debrid.com/premium",
    "torbox": "https://torbox.app/subscription",
    "alldebrid": "https://alldebrid.com/offer",
}


def renewal_url(service_name: str) -> str | None:
    """Devuelve el enlace de renovación de un servicio, si existe."""
    return RENEWAL_URLS.get(service_name)


def renewal_keyboard(service_name: str,
                     label: str = "💳 Renovar ahora") -> InlineKeyboardMarkup | None:
    """Teclado con un único botón de renovación (None si no hay enlace)."""
    url = renewal_url(service_name)
    if url is None:
        return None
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, url=url)]])
