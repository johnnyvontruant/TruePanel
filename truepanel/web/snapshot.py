"""Guided-recovery extension for Mission Control snapshots.

The mature snapshot implementation remains in :mod:`snapshot_base`. This
wrapper adds storage evidence needed by Project Kobayashi while preserving the
existing public ``SnapshotService`` import path.
"""

from __future__ import annotations

from typing import Any

from truepanel.guidance.storage_evidence import StorageRecoveryEvidenceProvider

from .snapshot_base import SnapshotService as _BaseSnapshotService


_UNHEALTHY_POOL_STATES = {
    "DEGRADED",
    "FAULTED",
    "OFFLINE",
    "UNAVAIL",
    "UNAVAILABLE",
}


def _safe_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _safe_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


class SnapshotService(_BaseSnapshotService):
    """Add read-only storage-recovery evidence to the existing snapshot."""

    def __init__(
        self,
        *args,
        storage_evidence_provider=None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.storage_evidence_provider = (
            storage_evidence_provider
            or StorageRecoveryEvidenceProvider()
        )

    def _storage_payload(
        self,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        payload = super()._storage_payload(state)

        # These values already exist in the collector. Publishing them here is
        # additive and performs no extra hardware I/O.
        payload["smart"] = _safe_list(state.get("smart"))
        payload["zfs_activity"] = _safe_dict(state.get("zfs_activity"))

        # HoloDeck/tests may provide deterministic member evidence directly.
        supplied_devices = state.get("storage_devices")
        if isinstance(supplied_devices, list):
            payload["devices"] = supplied_devices
            return payload

        payload["devices"] = []

        pools = _safe_list(payload.get("pools"))
        needs_resolution = any(
            isinstance(pool, dict)
            and str(
                pool.get("health")
                or pool.get("state")
                or ""
            ).strip().upper()
            in _UNHEALTHY_POOL_STATES
            for pool in pools
        )

        if not needs_resolution:
            return payload

        try:
            records = self.storage_evidence_provider.records()
        except (OSError, RuntimeError, TypeError, ValueError, AttributeError):
            records = []

        if isinstance(records, list):
            payload["devices"] = records

        return payload


__all__ = ["SnapshotService"]
