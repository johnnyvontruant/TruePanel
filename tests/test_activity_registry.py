from __future__ import annotations

from dataclasses import dataclass

import pytest

from truepanel.activity import (
    ActivityIntensity,
    ActivityObservation,
    ActivityProviderStatus,
    ActivityRegistry,
    ActivitySnapshot,
    ActivityState,
)


@dataclass
class StubProvider:
    source: str
    result: ActivitySnapshot

    def snapshot(self) -> ActivitySnapshot:
        return self.result


@dataclass
class ExplodingProvider:
    source: str

    def snapshot(self) -> ActivitySnapshot:
        raise RuntimeError("secret-token-must-never-escape")


def _observation(source: str, kind: str) -> ActivityObservation:
    return ActivityObservation(
        source=source,
        kind=kind,
        state=ActivityState.ACTIVE,
        title=kind,
        confidence=1.0,
        intensity=ActivityIntensity.MODERATE,
        evidence=(f"{source}.fixture",),
    )


def test_registry_isolates_failure_and_orders_sources() -> None:
    registry = ActivityRegistry(
        [
            StubProvider(
                "zfs",
                ActivitySnapshot(
                    source="zfs",
                    status=ActivityProviderStatus.AVAILABLE,
                    observations=(_observation("zfs", "zfs.scrub"),),
                ),
            ),
            ExplodingProvider("broken"),
            StubProvider(
                "plex",
                ActivitySnapshot(
                    source="plex",
                    status=ActivityProviderStatus.AVAILABLE,
                    observations=(_observation("plex", "video"),),
                ),
            ),
        ]
    )

    snapshot = registry.snapshot()

    assert [item.source for item in snapshot.providers] == [
        "broken",
        "plex",
        "zfs",
    ]
    assert snapshot.providers[0].status is ActivityProviderStatus.UNAVAILABLE
    assert [item.kind for item in snapshot.observations] == ["video", "zfs.scrub"]
    assert "secret-token-must-never-escape" not in str(snapshot.as_dict())


def test_registry_rejects_duplicate_sources() -> None:
    snapshot = ActivitySnapshot(
        source="plex",
        status=ActivityProviderStatus.AVAILABLE,
    )

    with pytest.raises(ValueError, match="sources must be unique"):
        ActivityRegistry(
            [
                StubProvider("plex", snapshot),
                StubProvider("plex", snapshot),
            ]
        )


def test_registry_contains_mismatched_provider_snapshot() -> None:
    registry = ActivityRegistry(
        [
            StubProvider(
                "plex",
                ActivitySnapshot(
                    source="zfs",
                    status=ActivityProviderStatus.AVAILABLE,
                ),
            )
        ]
    )

    snapshot = registry.snapshot()

    assert snapshot.providers[0].source == "plex"
    assert snapshot.providers[0].status is ActivityProviderStatus.UNAVAILABLE
    assert snapshot.observations == ()


def test_registry_enforces_per_provider_observation_budget() -> None:
    provider = StubProvider(
        "plex",
        ActivitySnapshot(
            source="plex",
            status=ActivityProviderStatus.AVAILABLE,
            observations=tuple(_observation("plex", f"video.{index}") for index in range(4)),
        ),
    )

    snapshot = ActivityRegistry(
        [provider],
        max_observations_per_provider=2,
    ).snapshot()

    assert [item.kind for item in snapshot.observations] == ["video.0", "video.1"]
    assert snapshot.truncated is True


def test_registry_enforces_combined_budget_deterministically() -> None:
    registry = ActivityRegistry(
        [
            StubProvider(
                "zfs",
                ActivitySnapshot(
                    source="zfs",
                    status=ActivityProviderStatus.AVAILABLE,
                    observations=(_observation("zfs", "zfs.scrub"),),
                ),
            ),
            StubProvider(
                "plex",
                ActivitySnapshot(
                    source="plex",
                    status=ActivityProviderStatus.AVAILABLE,
                    observations=(
                        _observation("plex", "video.0"),
                        _observation("plex", "video.1"),
                    ),
                ),
            ),
        ],
        max_observations=2,
    )

    snapshot = registry.snapshot()

    assert [item.kind for item in snapshot.observations] == ["video.0", "video.1"]
    assert snapshot.providers[1].source == "zfs"
    assert snapshot.providers[1].observations == ()
    assert snapshot.truncated is True


def test_registry_marks_provider_limit_truncation() -> None:
    registry = ActivityRegistry(
        [
            StubProvider(
                source,
                ActivitySnapshot(
                    source=source,
                    status=ActivityProviderStatus.AVAILABLE,
                ),
            )
            for source in ("a", "b", "c")
        ],
        max_providers=2,
    )

    snapshot = registry.snapshot()

    assert [item.source for item in snapshot.providers] == ["a", "b"]
    assert snapshot.truncated is True
