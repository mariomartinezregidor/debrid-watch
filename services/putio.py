"""Integración con put.io Account API v2."""

from datetime import datetime, timedelta, timezone
from typing import Any

from .base import DebridService, ProviderError


class PutioService(DebridService):
    name = "putio"
    endpoint = "https://api.put.io/v2/account/info"

    async def get_expiration(self, api_key: str) -> datetime:
        payload: dict[str, Any] = await self._get_json(
            self.endpoint, api_key, auth_scheme="Token"
        )
        info = payload.get("info", payload)
        if not isinstance(info, dict):
            raise ProviderError("Formato de respuesta de put.io inesperado")

        for field in ("expiration_date", "expirationDate", "premium_until", "premiumUntil",
                      "expires_at", "expiresAt", "subscription_expiration"):
            if info.get(field) is not None:
                return self.parse_datetime(info[field])

        # Versiones de la API han informado el periodo restante en días.
        for field in ("days_until_expiration", "daysUntilExpiration", "days_left"):
            if info.get(field) is not None:
                try:
                    days = max(0.0, float(info[field]))
                except (TypeError, ValueError, OverflowError) as exc:
                    raise ProviderError("Días restantes de put.io no válidos") from exc
                return datetime.now(timezone.utc) + timedelta(days=days)

        raise ProviderError("put.io no devolvió una fecha de caducidad compatible")
