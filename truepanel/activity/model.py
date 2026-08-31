"""Normalized, presentation-neutral activity evidence for Project OBSERVATORY."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

SCHEMA_VERSION = 1


class ActivityState(StrEnum):
    """Small common vocabulary for machine activity."""

    ACTIVE = "active"
    PLAYING = "playing"
    PAUSED = "paused"
    IDLE = "idle"
    UNKNOWN = "unknown"


class ActivityIntensity(StrEnum):
    """Coarse workload intensity without pretending to measure exact load."""

    IDLE = "idle"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    UNKNOWN = "unknown"


class ActivityProviderStatus(StrEnum):
    """Availability of one optional activity provider."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ActivityObservation:
    """Privacy-conscious activity evidence independent of any UI surface."""

    source: str
    kind: str
    state: ActivityState
    title: str
    confidence: float = 1.0
    intensity: ActivityIntensity = ActivityIntensity.UNKNOWN
    subtitle: str | None = None
    progress: float | None = None
    started_at: float | None = None
    context: Mapping[str, str] = field(default_factory=dict)
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for label, value in (
            ("source", self.source),
            ("kind", self.kind),
            ("title", self.title),
        ):
            if not str(value).strip():
                raise ValueError(f"activity {label} must not be empty")

        confidence = float(self.confidence)
        if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            raise ValueError("activity confidence must be finite and between 0 and 1")
        object.__setattr__(self, "confidence", confidence)

        if self.progress is not None:
            progress = float(self.progress)
            if not math.isfinite(progress) or not 0.0 <= progress <= 1.0:
                raise ValueError("activity progress must be finite and between 0 and 1")
            object.__setattr__(self, "progress", progress)

        if self.started_at is not None:
            started_at = float(self.started_at)
            if not math.isfinite(started_at) or started_at < 0.0:
                raise ValueError("activity started_at must be finite and non-negative")
            object.__setattr__(self, "started_at", started_at)

        safe_context = {
            str(key): str(value)
            for key, value in dict(self.context).items()
            if str(key).strip() and str(value).strip()
        }
        object.__setattr__(self, "context", MappingProxyType(safe_context))
        object.__setattr__(
            self,
            "evidence",
            tuple(str(item).strip() for item in self.evidence if str(item).strip()),
        )

    def as_dict(self) -> dict[str, object]:
        """Return a stable JSON-ready representation with no raw provider payload."""

        return {
            "schema_version": SCHEMA_VERSION,
            "source": self.source,
            "kind": self.kind,
            "state": self.state.value,
            "title": self.title,
            "confidence": self.confidence,
            "intensity": self.intensity.value,
            "subtitle": self.subtitle,
            "progress": self.progress,
            "started_at": self.started_at,
            "context": dict(self.context),
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class ActivitySnapshot:
    """One provider result with explicit availability and normalized observations."""

    source: str
    status: ActivityProviderStatus
    observations: tuple[ActivityObservation, ...] = ()

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("activity snapshot source must not be empty")
        if any(item.source != self.source for item in self.observations):
            raise ValueError("activity observation source must match snapshot source")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "source": self.source,
            "status": self.status.value,
            "observations": [item.as_dict() for item in self.observations],
        }


__all__ = [
    "SCHEMA_VERSION",
    "ActivityIntensity",
    "ActivityObservation",
    "ActivityProviderStatus",
    "ActivitySnapshot",
    "ActivityState",
]
