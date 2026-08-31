"""Bounded provider aggregation for Project OBSERVATORY."""

from __future__ import annotations

from dataclasses import dataclass

from .model import (
    ActivityObservation,
    ActivityProviderStatus,
    ActivitySnapshot,
)
from .provider import ActivityProvider

REGISTRY_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ActivityRegistrySnapshot:
    """One deterministic, bounded view across all configured providers."""

    providers: tuple[ActivitySnapshot, ...]
    truncated: bool = False

    @property
    def observations(self) -> tuple[ActivityObservation, ...]:
        return tuple(
            observation
            for provider in self.providers
            for observation in provider.observations
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": REGISTRY_SCHEMA_VERSION,
            "providers": [provider.as_dict() for provider in self.providers],
            "observations": [item.as_dict() for item in self.observations],
            "truncated": self.truncated,
        }


class ActivityRegistry:
    """Poll optional providers independently and contain provider failures."""

    def __init__(
        self,
        providers: tuple[ActivityProvider, ...] | list[ActivityProvider],
        *,
        max_providers: int = 16,
        max_observations_per_provider: int = 32,
        max_observations: int = 128,
    ) -> None:
        if max_providers < 1:
            raise ValueError("max_providers must be positive")
        if max_observations_per_provider < 1:
            raise ValueError("max_observations_per_provider must be positive")
        if max_observations < 1:
            raise ValueError("max_observations must be positive")

        ordered = sorted(
            tuple(providers),
            key=lambda provider: str(getattr(provider, "source", "")),
        )
        sources = [str(getattr(provider, "source", "")).strip() for provider in ordered]
        if any(not source for source in sources):
            raise ValueError("activity providers must declare a non-empty source")
        if len(set(sources)) != len(sources):
            raise ValueError("activity provider sources must be unique")

        self._providers = tuple(ordered[:max_providers])
        self._provider_limit_truncated = len(ordered) > max_providers
        self._max_observations_per_provider = int(max_observations_per_provider)
        self._max_observations = int(max_observations)

    @staticmethod
    def _unavailable(source: str) -> ActivitySnapshot:
        return ActivitySnapshot(
            source=source,
            status=ActivityProviderStatus.UNAVAILABLE,
        )

    def _poll(self, provider: ActivityProvider) -> ActivitySnapshot:
        source = str(provider.source).strip()
        try:
            snapshot = provider.snapshot()
        except Exception:
            # Optional providers are containment boundaries. Raw exception text
            # may contain credentials or private provider details, so it never
            # crosses into the normalized activity contract.
            return self._unavailable(source)

        if not isinstance(snapshot, ActivitySnapshot) or snapshot.source != source:
            return self._unavailable(source)
        return snapshot

    def snapshot(self) -> ActivityRegistrySnapshot:
        """Return a deterministic aggregate while enforcing observation budgets."""

        remaining = self._max_observations
        truncated = self._provider_limit_truncated
        bounded: list[ActivitySnapshot] = []

        for provider in self._providers:
            snapshot = self._poll(provider)
            observations = snapshot.observations
            allowed = min(self._max_observations_per_provider, remaining)
            selected = observations[:allowed]

            if len(selected) < len(observations):
                truncated = True

            bounded.append(
                ActivitySnapshot(
                    source=snapshot.source,
                    status=snapshot.status,
                    observations=selected,
                )
            )
            remaining -= len(selected)

        return ActivityRegistrySnapshot(
            providers=tuple(bounded),
            truncated=truncated,
        )


__all__ = [
    "REGISTRY_SCHEMA_VERSION",
    "ActivityRegistry",
    "ActivityRegistrySnapshot",
]
