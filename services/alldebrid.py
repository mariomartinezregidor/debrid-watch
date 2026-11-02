"""Integración con AllDebrid."""

from datetime import datetime
from typing import Any

from .base import AuthenticationError, DebridService, ProviderError


class AllDebridService(DebridService):
    name = "alldebrid"
    endpoint = "https://api.alldebrid.com/v4/user"

    async def get_expiration(self, api_key: str) -> datetime:
        payload = await self._get_json(self.endpoint, api_key, params={"agent": "DebridWatch"})
        status = payload.get("status")
        if status and status != "success":
            error: Any = payload.get("error", {})
            code = error.get("code") if isinstance(error, dict) else None
            if str(code).upper().startswith("AUTH") or str(code).lower() in {
                "invalid_apikey", "apikey_not_valid", "invalidapikey"
            }:
                raise AuthenticationError("AllDebrid rechazó la credencial")
            raise ProviderError("AllDebrid indicó un error en la respuesta")
        data = payload.get("data")
        user = data.get("user") if isinstance(data, dict) else None
        expiration = user.get("premiumUntil") if isinstance(user, dict) else None
        if expiration is None:
            raise ProviderError("AllDebrid no devolvió premiumUntil")
        return self.parse_datetime(expiration)
