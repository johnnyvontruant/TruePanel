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
from .registry import (
    REGISTRY_SCHEMA_VERSION,
    ActivityRegistry,
    ActivityRegistrySnapshot,
)
from .zfs import ZfsActivityProvider, normalize_zfs_activity

__all__ = [
    "SCHEMA_VERSION",
    "REGISTRY_SCHEMA_VERSION",
    "ActivityIntensity",
    "ActivityObservation",
    "ActivityProvider",
    "ActivityProviderStatus",
    "ActivityRegistry",
    "ActivityRegistrySnapshot",
    "ActivitySnapshot",
    "ActivityState",
    "PlexActivityProvider",
    "ZfsActivityProvider",
    "normalize_zfs_activity",
    "parse_plex_sessions",
]
