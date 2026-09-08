"""Cached Cargo Bay provider construction from TruePanel configuration."""

from __future__ import annotations

import time
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

from .resolver import (
    CargoResolver,
    ServarrClient,
    ServarrConfig,
)


class CachedCargoProvider:
    """Cache a CargoResolver snapshot for a short bounded interval."""

    def __init__(
        self,
        resolver: CargoResolver,
        *,
        cache_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.resolver = resolver
        self.cache_seconds = max(0.0, float(cache_seconds))
        self.clock = clock
        self._cached_at: float | None = None
        self._cached_payload: dict[str, Any] | None = None

    def snapshot(self) -> dict[str, Any]:
        now = self.clock()

        if (
            self._cached_at is not None
            and self._cached_payload is not None
            and now - self._cached_at < self.cache_seconds
        ):
            return deepcopy(self._cached_payload)

        payload = self.resolver.snapshot()

        if not isinstance(payload, dict):
            raise TypeError("Cargo resolver returned a non-dict payload")

        self._cached_at = now
        self._cached_payload = deepcopy(payload)

        return deepcopy(payload)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def provider_from_config(
    config: dict[str, Any],
    *,
    cache_clock: Callable[[], float] = time.monotonic,
    resolver_clock: Callable[[], float] = time.time,
) -> CachedCargoProvider | None:
    """Build Cargo Bay from portable TruePanel configuration."""

    mission = _dict(config.get("mission_control"))
    cargo = _dict(mission.get("cargo_bay"))

    if cargo.get("enabled") is not True:
        return None

    sonarr = _dict(cargo.get("sonarr"))
    radarr = _dict(cargo.get("radarr"))

    required = (
        _text(sonarr.get("url")),
        _text(sonarr.get("config_path")),
        _text(sonarr.get("host_prefix")),
        _text(radarr.get("url")),
        _text(radarr.get("config_path")),
        _text(radarr.get("host_prefix")),
    )

    if not all(required):
        return None

    sonarr_config = ServarrConfig(
        name="sonarr",
        base_url=_text(sonarr.get("url")),
        config_path=Path(_text(sonarr.get("config_path"))),
        media_prefix=(
            _text(sonarr.get("media_prefix"))
            or "/media/tv"
        ),
        host_prefix=Path(_text(sonarr.get("host_prefix"))),
    )

    radarr_config = ServarrConfig(
        name="radarr",
        base_url=_text(radarr.get("url")),
        config_path=Path(_text(radarr.get("config_path"))),
        media_prefix=(
            _text(radarr.get("media_prefix"))
            or "/media/movies"
        ),
        host_prefix=Path(_text(radarr.get("host_prefix"))),
    )

    resolver = CargoResolver(
        sonarr_client=ServarrClient(sonarr_config),
        radarr_client=ServarrClient(radarr_config),
        clock=resolver_clock,
        window_seconds=int(
            cargo.get("window_seconds") or 86400
        ),
        history_limit=int(
            cargo.get("history_limit") or 250
        ),
    )

    return CachedCargoProvider(
        resolver,
        cache_seconds=float(
            cargo.get("cache_seconds") or 60
        ),
        clock=cache_clock,
    )
