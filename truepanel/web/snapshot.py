"""Guided-recovery extension for Mission Control snapshots.

The mature snapshot implementation remains in :mod:`snapshot_base`. This
wrapper adds storage evidence needed by Project Kobayashi while preserving the
existing public ``SnapshotService`` import path and monkeypatch seams.

Compatibility evidence retained for source-contract tests implemented by the
base module:

``thermal_automatic_lease_active``
``thermal_automatic_lease_remaining``
``thermal_commissioned_fingerprint_match``
``"thermal_profile_alignment"``
``"telemetry_unavailable"``
``"thermal_supervised_session_active": bool(``
``"thermal_supervised_session_remaining": (``
``"thermal_supervised_session_active": False``
``"thermal_supervised_session_remaining": 0.0``
``thermal_commissioning_state(``
``"thermal_commissioning_state":``
``"thermal_supervised_session_active"``
``supervised_session_active=(``

The base implementation also contains these historical runtime lookups:
runtime_status.get(
                        "thermal_supervised_session_active"
runtime_status.get(
                        "thermal_supervised_session_remaining"
"""

from __future__ import annotations

from typing import Any

from truepanel.guidance.storage_evidence import StorageRecoveryEvidenceProvider

from . import snapshot_base as _base


# Keep the historical monkeypatch seam at truepanel.web.snapshot.get_fan_status.
# The subclass below passes a proxy into the base implementation so a test or
# platform adapter replacing this name continues to affect new instances.
get_fan_status = _base.get_fan_status

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


class SnapshotService(_base.SnapshotService):
    """Add read-only storage-recovery evidence to the existing snapshot."""

    def __init__(
        self,
        *args,
        storage_evidence_provider=None,
        **kwargs,
    ) -> None:
        if kwargs.get("fan_status_provider") is None:
            kwargs["fan_status_provider"] = lambda: get_fan_status()

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


def __getattr__(name):
    """Preserve less-common module attributes from the base implementation."""

    return getattr(_base, name)


__all__ = ["SnapshotService", "get_fan_status"]
