"""Integraciones con proveedores de debrid."""

from .alldebrid import AllDebridService
from .base import AuthenticationError, DebridService, ProviderError, RateLimitedError
from .real_debrid import RealDebridService
from .torbox import TorBoxService

SERVICE_CLASSES: dict[str, type[DebridService]] = {
    "real_debrid": RealDebridService,
    "torbox": TorBoxService,
    "alldebrid": AllDebridService,
}
SERVICE_LABELS = {
    "real_debrid": "Real-Debrid",
    "torbox": "TorBox",
    "alldebrid": "AllDebrid",
}

__all__ = ["AuthenticationError", "ProviderError", "RateLimitedError", "SERVICE_CLASSES", "SERVICE_LABELS"]
