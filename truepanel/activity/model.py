"""Normalized activity state shared by optional service integrations."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ActivityState(StrEnum):
    """Small common vocabulary for external activity."""

    PLAYING = "playing"
    PAUSED = "paused"
    ACTIVE = "active"
    IDLE = "idle"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ActivityItem:
    """Privacy-conscious, presentation-neutral activity snapshot."""

    source: str
    state: ActivityState
    title: str
    subtitle: str | None = None
    progress: float | None = None
    kind: str | None = None
    context: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("activity source must not be empty")
        if not self.title.strip():
            raise ValueError("activity title must not be empty")
        if self.progress is not None and not 0.0 <= self.progress <= 1.0:
            raise ValueError("activity progress must be between 0 and 1")

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-ready snapshot without credentials or raw payloads."""
        return {
            "source": self.source,
            "state": self.state.value,
            "title": self.title,
            "subtitle": self.subtitle,
            "progress": self.progress,
            "kind": self.kind,
            "context": dict(self.context),
        }
