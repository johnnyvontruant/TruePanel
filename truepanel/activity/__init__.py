"""Read-only activity providers for ambient TruePanel context.

Activity providers deliberately normalize external service state before it reaches
Mission Control or a physical display.  Providers must be optional and fail
closed: losing an integration must never affect core hardware monitoring.
"""

from .model import ActivityItem, ActivityState
from .plex import PlexActivityProvider, parse_plex_sessions

__all__ = [
    "ActivityItem",
    "ActivityState",
    "PlexActivityProvider",
    "parse_plex_sessions",
]
