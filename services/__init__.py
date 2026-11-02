"""Integraciones con proveedores de debrid."""

from .alldebrid import AllDebridService
from .base import AuthenticationError, DebridService, ProviderError, RateLimitedError
from .debridlink import DebridLinkService
from .offcloud import OffcloudService
from .premiumize import PremiumizeService
from .putio import PutioService
from .real_debrid import RealDebridService
from .torbox import TorBoxService

SERVICE_CLASSES: dict[str, type[DebridService]] = {
    "real_debrid": RealDebridService,
    "torbox": TorBoxService,
    "alldebrid": AllDebridService,
    "premiumize": PremiumizeService,
    "debridlink": DebridLinkService,
    "offcloud": OffcloudService,
    "putio": PutioService,
}
SERVICE_LABELS = {
    "real_debrid": "Real-Debrid",
    "torbox": "TorBox",
    "alldebrid": "AllDebrid",
    "premiumize": "Premiumize",
    "debridlink": "Debrid-Link",
    "offcloud": "Offcloud",
    "putio": "put.io",
}

__all__ = ["AuthenticationError", "ProviderError", "RateLimitedError", "SERVICE_CLASSES", "SERVICE_LABELS"]
