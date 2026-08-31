"""Read-only activity intelligence for Project OBSERVATORY.

Activity providers normalize optional service and host activity before it reaches
Mission Control, ORACLE, or physical presentation surfaces. Losing a provider
must never affect core monitoring or grant hardware-control authority.
"""

from .model import (
    SCHEMA_VERSION,
    ActivityIntensity,
    ActivityObservation,
    ActivityProviderStatus,
    ActivitySnapshot,
    ActivityState,
)
from .plex import PlexActivityProvider, parse_plex_sessions
from .provider import ActivityProvider

__all__ = [
    "SCHEMA_VERSION",
    "ActivityIntensity",
    "ActivityObservation",
    "ActivityProvider",
    "ActivityProviderStatus",
    "ActivitySnapshot",
    "ActivityState",
    "PlexActivityProvider",
    "parse_plex_sessions",
]
