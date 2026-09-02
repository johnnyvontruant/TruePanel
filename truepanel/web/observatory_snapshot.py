"""Mission Control snapshot enrichment for Project OBSERVATORY."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from truepanel.activity.provider import ActivityProvider
from truepanel.activity.web import mission_control_activity

from .snapshot import SnapshotService


class ObservatorySnapshotService(SnapshotService):
    """Attach a bounded, read-only OBSERVATORY block to status snapshots."""

    def __init__(
        self,
        *args: Any,
        activity_providers: Iterable[ActivityProvider] = (),
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._activity_providers = tuple(activity_providers)

    def status(self) -> dict[str, Any]:
        payload = super().status()
        result = dict(payload)
        result["activity"] = mission_control_activity(
            result,
            providers=self._activity_providers,
        )
        return result


__all__ = ["ObservatorySnapshotService"]
