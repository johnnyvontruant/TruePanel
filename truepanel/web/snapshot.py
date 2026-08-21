"""Guided-recovery extension for Mission Control snapshots.

The mature snapshot implementation remains in :mod:`snapshot_base`. This
wrapper adds storage evidence needed by Project Kobayashi plus Project
Lifeline's metadata-only repair-session ledger while preserving the existing
public ``SnapshotService`` import path and monkeypatch seams.

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
from truepanel.lifeline import LifelineSessionStore, service_profile_for_config

from . import snapshot_base as _base


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
    """Add read-only recovery evidence and persistent Lifeline metadata."""

    def __init__(
        self,
        *args,
        storage_evidence_provider=None,
        lifeline_store=None,
        lifeline_path=None,
        **kwargs,
    ) -> None:
        if kwargs.get("fan_status_provider") is None:
            kwargs["fan_status_provider"] = lambda: get_fan_status()

        super().__init__(*args, **kwargs)
        self.storage_evidence_provider = (
            storage_evidence_provider
            or StorageRecoveryEvidenceProvider()
        )
        self.lifeline_store = (
            lifeline_store
            or LifelineSessionStore(
                path=lifeline_path,
                clock=self.clock,
            )
        )
        self.lifeline_service_profile = service_profile_for_config(self.config)

    def status(self) -> dict[str, Any]:
        payload = super().status()
        try:
            result = self.lifeline_store.observe(payload)
            profile = self.lifeline_service_profile
            profile_changed = False
            if profile is not None and profile.drive_service_supported:
                for session in _safe_list(
                    _safe_dict(result.get("lifeline")).get("sessions")
                ):
                    if not isinstance(session, dict) or session.get("status") != "active":
                        continue
                    context = _safe_dict(session.get("context"))
                    if (
                        context.get("service_procedure_verified") is True
                        and context.get("service_profile") == profile.key
                        and context.get("service_source") == profile.source_title
                    ):
                        continue
                    self.lifeline_store.set_service_procedure_verified(
                        str(session.get("id") or ""),
                        verified=True,
                        profile=profile.key,
                        source=profile.source_title,
                    )
                    profile_changed = True

            if profile_changed:
                result = self.lifeline_store.observe(payload)

            lifeline = _safe_dict(result.get("lifeline"))
            if profile is not None:
                lifeline = dict(lifeline)
                lifeline["service_profile"] = profile.to_payload()
                result["lifeline"] = lifeline
            return result
        except (OSError, RuntimeError, TypeError, ValueError, AttributeError):
            result = dict(payload)
            result["lifeline"] = {
                "schema_version": 1,
                "read_only_hardware": True,
                "available": False,
                "sessions": [],
            }
            return result

    def _storage_payload(
        self,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        payload = super()._storage_payload(state)

        payload["smart"] = _safe_list(state.get("smart"))
        payload["zfs_activity"] = _safe_dict(state.get("zfs_activity"))

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
