"""Passive Host runtime ownership-mode selection."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from .readiness import CUTOVER_MARKER_PATH


class HostRuntimeMode(str, Enum):
    """Select whether the LCD embeds Host runtime or consumes an external one."""

    EMBEDDED = "embedded"
    EXTERNAL = "external"


def resolve_host_runtime_mode(
    *,
    marker_path: Path = CUTOVER_MARKER_PATH,
) -> HostRuntimeMode:
    """Resolve Host ownership passively from the ephemeral cutover marker."""

    return (
        HostRuntimeMode.EXTERNAL
        if marker_path.exists()
        else HostRuntimeMode.EMBEDDED
    )


__all__ = [
    "HostRuntimeMode",
    "resolve_host_runtime_mode",
]
