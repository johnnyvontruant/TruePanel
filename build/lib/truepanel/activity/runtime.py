"""Runtime construction of optional Project OBSERVATORY providers."""

from __future__ import annotations

import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .model import ActivityProviderStatus, ActivitySnapshot
from .plex import PlexActivityProvider
from .provider import ActivityProvider

PLEX_URL_ENV = "TRUEPANEL_OBSERVATORY_PLEX_URL"
PLEX_TOKEN_FILE_ENV = "TRUEPANEL_OBSERVATORY_PLEX_TOKEN_FILE"
_MAX_TOKEN_LENGTH = 4096


@dataclass(frozen=True)
class _UnavailableProvider:
    source: str

    def snapshot(self) -> ActivitySnapshot:
        return ActivitySnapshot(
            source=self.source,
            status=ActivityProviderStatus.UNAVAILABLE,
        )


def _read_private_token(path_value: str) -> str | None:
    candidate = Path(path_value).expanduser()
    if not candidate.is_absolute():
        return None

    try:
        details = candidate.lstat()
        if stat.S_ISLNK(details.st_mode):
            return None
        if not stat.S_ISREG(details.st_mode):
            return None
        if stat.S_IMODE(details.st_mode) & 0o077:
            return None
        token = candidate.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None

    if not token or len(token) > _MAX_TOKEN_LENGTH or "\x00" in token:
        return None
    return token


def activity_providers_from_environment(
    environment: Mapping[str, str] | None = None,
) -> tuple[ActivityProvider, ...]:
    """Build optional read-only providers without exposing credentials.

    Plex uses a path in the Mission Control environment, never the token itself.
    The referenced token must be an absolute, regular, non-symlink file with no
    group or other permission bits. Partial or invalid configuration becomes an
    unavailable provider instead of failing the Mission Control process.
    """

    values = os.environ if environment is None else environment
    base_url = str(values.get(PLEX_URL_ENV, "")).strip()
    token_file = str(values.get(PLEX_TOKEN_FILE_ENV, "")).strip()

    if not base_url and not token_file:
        return ()
    if not base_url or not token_file:
        return (_UnavailableProvider("plex"),)

    token = _read_private_token(token_file)
    if token is None:
        return (_UnavailableProvider("plex"),)

    try:
        provider: ActivityProvider = PlexActivityProvider(base_url, token)
    except (TypeError, ValueError):
        return (_UnavailableProvider("plex"),)
    return (provider,)


__all__ = [
    "PLEX_TOKEN_FILE_ENV",
    "PLEX_URL_ENV",
    "activity_providers_from_environment",
]
