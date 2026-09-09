"""Mission Control snapshot extension for Project SENTINEL.

This module composes existing Mission Control evidence with a cached, read-only
TrueNAS topology provider. It does not change the established snapshot module,
which keeps the integration easy to disable or roll back while SENTINEL
matures.
"""

from __future__ import annotations

from typing import Any

from truepanel.health import ServiceStatusProvider
from truepanel.sentinel import (
    CachedTopologyProvider,
    build_sentinel_snapshot,
)

from .snapshot import SnapshotService as _SnapshotService


class SentinelSnapshotService(_SnapshotService):
    """Attach bounded topology evidence and deterministic SENTINEL output."""

    def __init__(
        self,
        *args,
        sentinel_topology_provider=None,
        **kwargs,
    ) -> None:
        if kwargs.get("service_status_provider") is None:
            kwargs["service_status_provider"] = ServiceStatusProvider()

        super().__init__(*args, **kwargs)
        self.sentinel_topology_provider = (
            sentinel_topology_provider
            if sentinel_topology_provider is not None
            else CachedTopologyProvider()
        )

    @staticmethod
    def _topology_unavailable() -> dict[str, Any]:
        return {
            "schema_version": 1,
            "read_only": True,
            "source": "truenas.middleware",
            "available": False,
            "datasets": [],
            "applications": [],
            "relationships": [],
        }

    def _sentinel_topology_payload(self) -> dict[str, Any]:
        provider = self.sentinel_topology_provider

        if provider is None:
            return self._topology_unavailable()

        try:
            payload = provider.snapshot()
        except (
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
            AttributeError,
        ):
            return self._topology_unavailable()

        if not isinstance(payload, dict):
            return self._topology_unavailable()

        result = dict(payload)
        result.setdefault("available", True)
        result["read_only"] = True
        return result

    def status(self) -> dict[str, Any]:
        payload = super().status()
        payload = payload if isinstance(payload, dict) else {}
        result = dict(payload)
        result["sentinel_topology"] = self._sentinel_topology_payload()

        try:
            result["sentinel"] = build_sentinel_snapshot(result)
        except (TypeError, ValueError, ArithmeticError, AttributeError):
            result["sentinel"] = {
                "schema_version": 1,
                "read_only": True,
                "control_authority": False,
                "graph": {"nodes": [], "edges": []},
                "assessment": {
                    "state": "UNKNOWN",
                    "claims": [],
                    "unknowns": [
                        "SENTINEL could not build a deterministic assessment "
                        "from the current snapshot."
                    ],
                },
                "impact_reports": [],
                "available": False,
            }

        return result


__all__ = ["SentinelSnapshotService"]
