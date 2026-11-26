"""Avisos inteligentes de caducidad y frescura de las consultas.

Separa dos decisiones que antes estaban mezcladas en el scheduler:

* qué aviso corresponde (umbrales configurables, deduplicación por umbral);
* si merece la pena volver a consultar la API o basta con el dato reciente
  almacenado en la base de datos.

Los umbrales se expresan en días naturales completos redondeados hacia arriba,
igual que `days_remaining`, para no perder el último día de cada umbral.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from handlers.common import days_remaining, format_date
from renewal import renewal_url
from services import SERVICE_LABELS

DEFAULT_THRESHOLDS: tuple[int, ...] = (14, 7, 3, 1)
URGENT_DAYS = 7


@dataclass(frozen=True, slots=True)
class Alert:
    """Aviso listo para enviar, con el identificador del umbral ya aplicado."""

    threshold: str
    text: str


def _plural(days: int) -> str:
    return "día" if days == 1 else "días"


def build_alert(service_name: str, expiration: datetime,
                thresholds: tuple[int, ...] = DEFAULT_THRESHOLDS) -> Alert | None:
    """Devuelve el aviso correspondiente o None si aún no toca avisar."""
    label = SERVICE_LABELS.get(service_name, service_name)
    remaining = days_remaining(expiration)
    date_text = format_date(expiration)

    if remaining <= 0:
        threshold = "expired"
        text = f"❌ Tu suscripción de {label} ha caducado ({date_text})."
    elif remaining == 1:
        threshold = "1"
        text = f"⚠️ Tu suscripción de {label} caduca mañana ({date_text})."
    else:
        # Se elige el umbral más específico alcanzado: si el job se saltó un
        # aviso intermedio no se compensa enviando varios avisos seguidos.
        reached = [days for days in sorted(thresholds) if days >= remaining]
        if not reached:
            return None
        days = reached[0]
        threshold = str(days)
        text = f"⚠️ Tu suscripción de {label} caduca en {days} {_plural(days)} ({date_text})."

    url = renewal_url(service_name)
    if url:
        text += f"\n💳 Renueva aquí: {url}"
    text += "\nSi ya renovaste, actualiza la API Key desde /mis_servicios."
    return Alert(threshold=threshold, text=text)


def needs_refresh(last_checked_at: datetime | None, expiration: datetime | None,
                  now: datetime | None = None, *, freshness_hours: int = 16,
                  urgent_hours: int = 2) -> bool:
    """Indica si la fecha guardada está demasiado anticuada para fiarse de ella.

    Las cuentas próximas a caducar se comprueban más a menudo; las que tienen
    semanas por delante reutilizan el último dato durante más tiempo. Así se
    reducen las llamadas a la API sin retrasar los avisos urgentes.
    """
    if expiration is None or last_checked_at is None:
        return True
    current = now or datetime.now(timezone.utc)
    age_hours = (current - last_checked_at).total_seconds() / 3600
    window = urgent_hours if days_remaining(expiration, current) <= URGENT_DAYS else freshness_hours
    return age_hours >= window
