"""Integración con TorBox (v1 API user/me)."""

from datetime import datetime
from typing import Any

from .base import DebridService, ProviderError


class TorBoxService(DebridService):
    name = "torbox"
    endpoint = "https://api.torbox.app/v1/api/user/me"

    async def get_expiration(self, api_key: str) -> datetime:
        payload = await self._get_json(self.endpoint, api_key)
        # La API suele devolver {success, data:{premium_expires_at}}. Se
        # aceptan alias documentados/observados para tolerar cambios de versión.
        data: Any = payload.get("data", payload)
        if not isinstance(data, dict):
            raise ProviderError("Formato de respuesta de TorBox inesperado")
        expiration = next((data.get(field) for field in (
            "premium_expires_at", "premium_expires", "expires_at", "expiration", "premium_until"
        ) if data.get(field) is not None), None)
        if expiration is None:
            raise ProviderError("TorBox no devolvió una fecha de caducidad conocida")
        return self.parse_datetime(expiration)
