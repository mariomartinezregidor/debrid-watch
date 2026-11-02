"""Integración con Real-Debrid."""

from datetime import datetime
from typing import Any

from .base import DebridService, ProviderError


class RealDebridService(DebridService):
    name = "real_debrid"
    endpoint = "https://api.real-debrid.com/rest/1.0/user"

    async def get_expiration(self, api_key: str) -> datetime:
        data: dict[str, Any] = await self._get_json(self.endpoint, api_key)
        expiration = data.get("expiration")
        if not expiration:
            raise ProviderError("Real-Debrid no devolvió una fecha de caducidad")
        return self.parse_datetime(expiration)
