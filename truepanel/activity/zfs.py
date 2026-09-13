"""Read-only ZFS maintenance activity provider for Project OBSERVATORY.

The provider consumes TruePanel's existing normalized ``zfs_activity`` evidence
rather than executing another ``zpool`` command.  It deliberately ignores raw
status lines so pool names, paths, or future command-output details never become
part of the activity contract by accident.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import Any

from .model import (
    ActivityIntensity,
    ActivityObservation,
    ActivityProviderStatus,
    ActivitySnapshot,
    ActivityState,
)

ActivityReader = Callable[[], Mapping[str, Any]]


def _progress(value: Any) -> float | None:
    """Normalize a trustworthy 0-100 percentage to 0-1, otherwise unknown."""

    if isinstance(value, bool):
        return None
    try:
        percent = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(percent) or not 0.0 <= percent <= 100.0:
        return None
    return percent / 100.0


def normalize_zfs_activity(activity: Any) -> tuple[ActivityObservation, ...]:
    """Translate TruePanel collector evidence into presentation-neutral activity.

    Only exact boolean evidence can assert that an operation is active.  If
    both operations are active, the collector's single percentage cannot be
    safely attributed to either one, so progress remains explicitly unknown.
    """

    if not isinstance(activity, Mapping):
        return ()

    scrub = activity.get("scrub_running") is True
    resilver = activity.get("resilver_running") is True
    shared_progress = _progress(activity.get("percent"))
    progress = shared_progress if scrub ^ resilver else None

    observations: list[ActivityObservation] = []

    if scrub:
        observations.append(
            ActivityObservation(
                source="zfs",
                kind="zfs.scrub",
                state=ActivityState.ACTIVE,
                title="ZFS scrub",
                subtitle="Storage integrity maintenance",
                confidence=1.0,
                intensity=ActivityIntensity.MODERATE,
                progress=progress,
                evidence=("storage.zfs_activity.scrub_running",),
            )
        )

    if resilver:
        observations.append(
            ActivityObservation(
                source="zfs",
                kind="zfs.resilver",
                state=ActivityState.ACTIVE,
                title="ZFS resilver",
                subtitle="Storage redundancy recovery",
                confidence=1.0,
                intensity=ActivityIntensity.HIGH,
                progress=progress,
                evidence=("storage.zfs_activity.resilver_running",),
            )
        )

    return tuple(observations)


class ZfsActivityProvider:
    """Normalize existing TruePanel ZFS evidence without new command authority."""

    source = "zfs"

    def __init__(self, activity_reader: ActivityReader) -> None:
        if not callable(activity_reader):
            raise TypeError("ZFS activity_reader must be callable")
        self._activity_reader = activity_reader

    def snapshot(self) -> ActivitySnapshot:
        """Return current ZFS maintenance activity and fail closed on source loss."""

        try:
            activity = self._activity_reader()
            if not isinstance(activity, Mapping):
                raise TypeError("ZFS activity evidence must be a mapping")
            observations = normalize_zfs_activity(activity)
        except Exception:
            return ActivitySnapshot(
                source=self.source,
                status=ActivityProviderStatus.UNAVAILABLE,
            )

        return ActivitySnapshot(
            source=self.source,
            status=ActivityProviderStatus.AVAILABLE,
            observations=observations,
        )


__all__ = ["ZfsActivityProvider", "normalize_zfs_activity"]
