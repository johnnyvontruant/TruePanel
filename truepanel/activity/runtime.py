"""Runtime construction of optional Project OBSERVATORY providers."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from .model import ActivityProviderStatus, ActivitySnapshot
from .plex import PlexActivityProvider
from .provider import ActivityProvider

PLEX_URL_ENV = "TRUEPANEL_OBSERVATORY_PLEX_URL"
PLEX_TOKEN_ENV = "TRUEPANEL_OBSERVATORY_PLEX_TOKEN"


@dataclass(frozen=True)
class _UnavailableProvider:
    source: str

    def snapshot(self) -> ActivitySnapshot:
        return ActivitySnapshot(
            source=self.source,
            status=ActivityProviderStatus.UNAVAILABLE,
        )


def activity_providers_from_environment(
    environment: Mapping[str, str] | None = None,
) -> tuple[ActivityProvider, ...]:
    """Build optional read-only providers without exposing configuration.

    OBSERVATORY is optional to Mission Control. Missing configuration disables
    the provider. Partial or invalid Plex configuration becomes an unavailable
    provider instead of failing the Mission Control process.
    """

    values = os.environ if environment is None else environment
    base_url = str(values.get(PLEX_URL_ENV, "")).strip()
    token = str(values.get(PLEX_TOKEN_ENV, "")).strip()

    if not base_url and not token:
        return ()
    if not base_url or not token:
        return (_UnavailableProvider("plex"),)

    try:
        provider: ActivityProvider = PlexActivityProvider(base_url, token)
    except (TypeError, ValueError):
        return (_UnavailableProvider("plex"),)
    return (provider,)


__all__ = [
    "PLEX_TOKEN_ENV",
    "PLEX_URL_ENV",
    "activity_providers_from_environment",
]
