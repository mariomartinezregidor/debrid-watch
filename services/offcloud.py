"""Integración con Offcloud Account API."""

from typing import Any

from .base import DebridService, ProviderError


_EXPIRATION_FIELDS = (
    "premium_until", "premiumUntil", "premium_expires_at", "premiumExpiresAt",
    "subscription_expires_at", "subscriptionExpiresAt", "expiration_date",
    "expirationDate", "expires_at", "expiresAt", "expiration", "expires",
    "expiry", "premium_expiration", "premiumExpiration", "plan_expires_at",
)


def _find_expiration(value: Any) -> Any | None:
    """Busca campos de expiración conocidos en el objeto de cuenta/documentación."""
    if isinstance(value, dict):
        for field in _EXPIRATION_FIELDS:
            if value.get(field) is not None:
                return value[field]
        for child in value.values():
            found = _find_expiration(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_expiration(child)
            if found is not None:
                return found
    return None


class OffcloudService(DebridService):
    name = "offcloud"
    # La API de cuenta vigente acepta la API Key como Bearer.
    endpoint = "https://offcloud.com/api/account/info"

    async def get_expiration(self, api_key: str) -> datetime:
        payload = await self._get_json(self.endpoint, api_key)
        expiration = _find_expiration(payload)
        if expiration is None:
            raise ProviderError(
                "Offcloud validó la cuenta, pero no devolvió un campo de caducidad compatible"
            )
        try:
            return self.parse_datetime(expiration)
        except (ValueError, OverflowError) as exc:
            raise ProviderError("La fecha de caducidad de Offcloud no es válida") from exc
