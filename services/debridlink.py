"""Integración con Debrid-Link API v2."""

from datetime import datetime, timedelta, timezone
from typing import Any

from .base import AuthenticationError, DebridService, ProviderError


class DebridLinkService(DebridService):
    name = "debridlink"
    endpoint = "https://debrid-link.com/api/v2/account/infos"

    async def get_expiration(self, api_key: str) -> datetime:
        payload: dict[str, Any] = await self._get_json(self.endpoint, api_key)
        if payload.get("success") is not True:
            error = str(payload.get("error", "")).lower()
            if error in {"badtoken", "notoken", "invalid_token", "unauthorized"}:
                raise AuthenticationError("Debrid-Link rechazó la credencial")
            raise ProviderError("Debrid-Link devolvió un error en la respuesta")
        value = payload.get("value")
        if not isinstance(value, dict) or "premiumLeft" not in value:
            raise ProviderError("Debrid-Link no devolvió premiumLeft")
        try:
            remaining_seconds = max(0, int(value["premiumLeft"]))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ProviderError("premiumLeft de Debrid-Link no es válido") from exc
        # La API informa segundos restantes, no una fecha absoluta.
        return datetime.now(timezone.utc) + timedelta(seconds=remaining_seconds)
