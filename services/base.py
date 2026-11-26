"""Cliente HTTP común: caché por credencial, limitación y backoff ante 429."""

from __future__ import annotations

import asyncio
import hashlib
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx


class ProviderError(Exception):
    """Error del proveedor que no implica necesariamente una clave inválida."""


class AuthenticationError(ProviderError):
    """La credencial fue rechazada (HTTP 401/403 o equivalente)."""


class RateLimitedError(ProviderError):
    """El proveedor limitó las consultas; ``retry_after`` viene del cabecera."""

    def __init__(self, message: str = "El proveedor limitó temporalmente las consultas",
                 *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    value: datetime
    expires_at: float


class DebridService(ABC):
    name: str
    # Un tiempo acotado mantiene las consultas interactivas ágiles incluso
    # cuando un proveedor deja de responder.
    timeout = httpx.Timeout(1.8, connect=1.0)
    # Valores por defecto; se pueden ajustar desde Settings al construir el bot.
    default_cache_ttl = 900.0
    default_min_interval = 1.0
    default_max_cooldown = 300.0
    max_cache_entries = 512

    def __init__(self, *, cache_ttl: float | None = None,
                 min_interval: float | None = None) -> None:
        self.cache_ttl = float(self.default_cache_ttl if cache_ttl is None else cache_ttl)
        self.min_interval = float(self.default_min_interval if min_interval is None else min_interval)
        self.max_cooldown = float(self.default_max_cooldown)
        self._client = httpx.AsyncClient(timeout=self.timeout, follow_redirects=False)
        # La cerradura serialize TODAS las peticiones de este proveedor: evita
        # que un lote de usuarios supere el límite por segundos.
        self._request_lock = asyncio.Lock()
        self._last_request = 0.0
        self._cooldown_until = 0.0
        self._consecutive_429 = 0
        self._cache: dict[str, _CacheEntry] = {}
        self._pending: dict[str, asyncio.Task[datetime]] = {}
        self._cache_lock = asyncio.Lock()

    async def close(self) -> None:
        await self._client.aclose()
        for task in tuple(self._pending.values()):
            if not task.done():
                task.cancel()

    @staticmethod
    def _key_digest(api_key: str) -> str:
        # La caché nunca guarda la credencial en claro, solo su huella.
        return hashlib.sha256(api_key.encode("utf-8")).hexdigest()

    async def _get_json(self, url: str, api_key: str, *, params: dict[str, str] | None = None,
                        auth_scheme: str | None = "Bearer") -> dict[str, Any]:
        # Se mantiene la cerradura durante la petición para que el espaciado
        # entre llamadas sea real y no se acumulen esperas simultáneas.
        async with self._request_lock:
            now = time.monotonic()
            remaining = self._cooldown_until - now
            if remaining > 0:
                raise RateLimitedError(retry_after=remaining)
            wait = self.min_interval - (now - self._last_request)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request = time.monotonic()
            try:
                headers = {"Accept": "application/json"}
                if auth_scheme:
                    headers["Authorization"] = f"{auth_scheme} {api_key}"
                response = await self._client.get(url, headers=headers, params=params)
            except httpx.HTTPError as exc:
                raise ProviderError("No se pudo conectar con el servicio") from exc

            if response.status_code in (401, 403):
                raise AuthenticationError("El proveedor rechazó la credencial")
            if response.status_code == 429:
                self._consecutive_429 += 1
                # Preferir Retry-After del proveedor; si no lo envía, backoff
                # exponencial con jitter para no sincronizar a todos los users.
                fallback = min(self.min_interval * (2 ** min(self._consecutive_429 - 1, 5)), 30.0)
                delay = self.parse_retry_after_seconds(response.headers.get("Retry-After"))
                delay = min(delay if delay is not None else fallback + random.uniform(0, 0.5),
                            self.max_cooldown)
                self._cooldown_until = time.monotonic() + delay
                raise RateLimitedError(retry_after=delay)
            if response.status_code >= 400:
                raise ProviderError(f"El proveedor respondió HTTP {response.status_code}")
            self._consecutive_429 = 0
            try:
                payload = response.json()
            except ValueError as exc:
                raise ProviderError("El proveedor devolvió una respuesta no válida") from exc
        if not isinstance(payload, dict):
            raise ProviderError("Formato de respuesta inesperado")
        return payload

    async def get_cached_expiration(self, api_key: str, *, ttl: float | None = None,
                                    force: bool = False) -> datetime:
        """Devuelve la caducidad reutilizando respuestas recientes.

        Varias coroutines que consulten la misma clave comparten una única
        petición en vuelo. ``force=True`` ignora la caché pero no duplica una
        consulta que ya esté en curso.
        """
        digest = self._key_digest(api_key)
        lifetime = self.cache_ttl if ttl is None else max(0.0, float(ttl))
        now = time.monotonic()
        async with self._cache_lock:
            entry = self._cache.get(digest)
            if not force and entry is not None and entry.expires_at > now:
                return entry.value
            task = self._pending.get(digest)
            if task is None:
                task = asyncio.create_task(self.get_expiration(api_key),
                                           name=f"{self.name}-expiration")
                self._pending[digest] = task
        try:
            value = await asyncio.shield(task)
        finally:
            async with self._cache_lock:
                if self._pending.get(digest) is task:
                    del self._pending[digest]
        async with self._cache_lock:
            if lifetime > 0:
                if len(self._cache) >= self.max_cache_entries:
                    cutoff = time.monotonic()
                    self._cache = {key: item for key, item in self._cache.items()
                                   if item.expires_at > cutoff}
                    if self._cache and len(self._cache) >= self.max_cache_entries:
                        self._cache.pop(next(iter(self._cache)))
                self._cache[digest] = _CacheEntry(value, time.monotonic() + lifetime)
        return value

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
    def parse_retry_after_seconds(value: str | None) -> float | None:
        """Acepta tanto segundos como una fecha HTTP en ``Retry-After``."""
        if not value:
            return None
        value = value.strip()
        try:
            return max(0.0, float(value))
        except ValueError:
            pass
        try:
            when = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
