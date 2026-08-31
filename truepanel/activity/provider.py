"""Activity-provider protocol for Project OBSERVATORY."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .model import ActivitySnapshot


@runtime_checkable
class ActivityProvider(Protocol):
    """Minimal read-only contract implemented by optional activity sources."""

    source: str

    def snapshot(self) -> ActivitySnapshot:
        """Return a normalized snapshot without granting control authority."""
        ...


__all__ = ["ActivityProvider"]
