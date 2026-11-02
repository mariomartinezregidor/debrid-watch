"""Integración con Premiumize.me Account API."""

from datetime import datetime, timezone
from typing import Any

from .base import AuthenticationError, DebridService, ProviderError


class PremiumizeService(DebridService):
    name = "premiumize"
    endpoint = "https://www.premiumize.me/api/account/info"

    async def get_expiration(self, api_key: str) -> datetime:
        payload: dict[str, Any] = await self._get_json(self.endpoint, api_key)
        if payload.get("status") != "success":
            code = str(payload.get("code", "")).lower()
            if code in {"authentication_failed", "permission_denied", "invalid_api_key"}:
                raise AuthenticationError("Premiumize rechazó la credencial")
            raise ProviderError("Premiumize devolvió un error en la respuesta")
        if "premium_until" not in payload:
            raise ProviderError("Premiumize no devolvió premium_until")
        expiration = payload["premium_until"]
        # La API documenta null para las cuentas gratuitas: son válidas, pero
        # no tienen periodo premium vigente.
        return datetime.now(timezone.utc) if expiration is None else self.parse_datetime(expiration)
