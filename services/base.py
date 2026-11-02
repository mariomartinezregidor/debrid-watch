"""Cliente HTTP común, limitación por proveedor y errores normalizados."""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx


class ProviderError(Exception):
    """Error del proveedor que no implica necesariamente una clave inválida."""


class AuthenticationError(ProviderError):
    """La credencial fue rechazada (HTTP 401/403 o equivalente)."""


class RateLimitedError(ProviderError):
    """El proveedor respondió con HTTP 429."""


class DebridService(ABC):
    name: str
    # Un tiempo acotado mantiene las consultas interactivas ágiles incluso
    # cuando un proveedor deja de responder.
    timeout = httpx.Timeout(1.8, connect=1.0)

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=self.timeout, follow_redirects=False)
        self._request_lock = asyncio.Lock()
        self._last_request = 0.0

    async def close(self) -> None:
        await self._client.aclose()

    async def _get_json(self, url: str, api_key: str, *, params: dict[str, str] | None = None) -> dict[str, Any]:
        # Una petición por segundo por instancia/proveedor; el bloqueo también
        # evita que un lote de usuarios exceda el límite en paralelo.
        async with self._request_lock:
            wait = 1.0 - (time.monotonic() - self._last_request)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request = time.monotonic()
            try:
                response = await self._client.get(
                    url, headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"}, params=params
                )
            except httpx.HTTPError as exc:
                raise ProviderError("No se pudo conectar con el servicio") from exc
        if response.status_code in (401, 403):
            raise AuthenticationError("El proveedor rechazó la credencial")
        if response.status_code == 429:
            raise RateLimitedError("El proveedor limitó temporalmente las consultas")
        if response.status_code >= 400:
            raise ProviderError(f"El proveedor respondió HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError("El proveedor devolvió una respuesta no válida") from exc
        if not isinstance(payload, dict):
            raise ProviderError("Formato de respuesta inesperado")
        return payload

    @abstractmethod
    async def get_expiration(self, api_key: str) -> datetime:
        """Valida la clave y devuelve la caducidad en UTC."""

    @staticmethod
    def parse_datetime(value: Any) -> datetime:
        if isinstance(value, (int, float)):
            result = datetime.fromtimestamp(value, tz=timezone.utc)
        elif isinstance(value, str):
            try:
                result = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ProviderError("Fecha de caducidad con formato inesperado") from exc
            if result.tzinfo is None:
                result = result.replace(tzinfo=timezone.utc)
        else:
            raise ProviderError("El proveedor no informó una fecha de caducidad")
        return result.astimezone(timezone.utc)

    @staticmethod
    def parse_retry_after(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
