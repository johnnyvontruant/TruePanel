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

from pathlib import Path
from typing import Any

from truepanel.guidance.storage_evidence import (
    StorageRecoveryEvidenceProvider,
    normalize_device,
)
from truepanel.lifeline import (
    DriveFingerprintProvider,
    DriveFingerprintStore,
    LifelineSessionStore,
    ReplacementCandidateProvider,
    service_profile_for_config,
)

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


def _smart_counter(record: dict[str, Any], key: str) -> int:
    try:
        return int(record.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _smart_requires_evidence(record: Any) -> bool:
    if not isinstance(record, dict):
        return False

    if str(record.get("health") or "").strip().upper() == "FAILED":
        return True

    if any(
        _smart_counter(record, key) > 0
        for key in (
            "reallocated",
            "pending",
            "offline_uncorrectable",
            "reported_uncorrect",
            "media_errors",
        )
    ):
        return True

    warning = str(
        record.get("critical_warning") or ""
    ).strip().lower()
    return warning not in {"", "0", "0x0", "0x00"}


def _session_by_id(payload: dict[str, Any], session_id: str) -> dict[str, Any] | None:
    for session in _safe_list(_safe_dict(payload.get("lifeline")).get("sessions")):
        if isinstance(session, dict) and str(session.get("id") or "") == session_id:
            return session
    return None


def _fingerprint_matches_session(
    session: dict[str, Any],
    fingerprint: dict[str, Any],
) -> bool:
    original = _safe_dict(session.get("original_fault"))
    if fingerprint.get("verified") is not True or fingerprint.get("conflicted") is True:
        return False
    if str(original.get("device") or "").strip():
        return False

    member_id = str(original.get("member_id") or "").strip()
    pool = str(original.get("pool") or "").strip()
    if not member_id or member_id != str(fingerprint.get("member_guid") or "").strip():
        return False
    if not pool or pool != str(fingerprint.get("pool") or "").strip():
        return False

    historical_path = str(original.get("historical_path") or "").strip()
    partuuid = str(fingerprint.get("partuuid") or "").strip()
    if historical_path:
        expected_path = f"/dev/disk/by-partuuid/{partuuid}" if partuuid else ""
        if not expected_path or historical_path != expected_path:
            return False

    try:
        bay = int(fingerprint.get("physical_bay"))
        capacity = int(fingerprint.get("capacity_bytes"))
    except (TypeError, ValueError):
        return False

    serial_last4 = str(fingerprint.get("serial_last4") or "").strip()
    mapping_source = str(fingerprint.get("mapping_source") or "").strip()
    return bool(
        bay > 0
        and capacity > 0
        and serial_last4
        and mapping_source == "kernel"
    )


def _replacement_fault_for_session(session: dict[str, Any]) -> dict[str, Any]:
    """Return discovery evidence enriched only by verified session provenance.

    The immutable original fault deliberately remains unchanged when a removed
    disk has no current Linux device or bay. Replacement discovery may still
    use the independently verified historical target from the latest repair
    evaluation so that a same-slot workflow remains scoped to that bay.
    """

    original = dict(_safe_dict(session.get("original_fault")))

    drive_identity = _safe_dict(session.get("drive_identity"))
    if drive_identity:
        original["drive_identity"] = dict(drive_identity)

    repair = _safe_dict(session.get("last_session"))
    target = _safe_dict(repair.get("target"))

    original_member = str(original.get("member_id") or "").strip()
    target_member = str(target.get("member_id") or "").strip()
    target_source = str(target.get("physical_identity_source") or "").strip()
    original_device = str(original.get("device") or "").strip()

    if not (
        original_member
        and target_member == original_member
        and not original_device
        and target_source == "historical_verified"
    ):
        return original

    bay = target.get("bay")
    if bay is not None:
        original["bay"] = bay

    if not str(original.get("serial_last4") or "").strip():
        serial_last4 = str(
            target.get("physical_identity_serial_last4") or ""
        ).strip()
        if serial_last4:
            original["serial_last4"] = serial_last4

    if original.get("capacity_bytes") in (None, ""):
        capacity = target.get("capacity_bytes")
        if capacity not in (None, ""):
            original["capacity_bytes"] = capacity
            original["capacity_source"] = target.get("capacity_source")

    return original


class SnapshotService(_base.SnapshotService):
    """Add read-only recovery evidence and persistent Lifeline metadata."""

    def __init__(
        self,
        *args,
        storage_evidence_provider=None,
        replacement_candidate_provider=None,
        drive_fingerprint_provider=None,
        drive_fingerprint_store=None,
        drive_fingerprint_path=None,
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
        self.replacement_candidate_provider = (
            replacement_candidate_provider
            or ReplacementCandidateProvider()
        )
        self.lifeline_store = (
            lifeline_store
            or LifelineSessionStore(
                path=lifeline_path,
                clock=self.clock,
            )
        )

        if drive_fingerprint_path is None and lifeline_path is not None:
            drive_fingerprint_path = Path(lifeline_path).with_name(
                "drive-fingerprints.json"
            )
        self.drive_fingerprint_provider = (
            drive_fingerprint_provider
            or DriveFingerprintProvider(clock=self.clock)
        )
        self.drive_fingerprint_store = (
            drive_fingerprint_store
            or DriveFingerprintStore(
                path=drive_fingerprint_path,
                clock=self.clock,
            )
        )
        self.lifeline_service_profile = service_profile_for_config(self.config)

    def _record_healthy_fingerprints(self) -> None:
        try:
            fingerprints = self.drive_fingerprint_provider.fingerprints()
            self.drive_fingerprint_store.record(fingerprints)
        except (OSError, RuntimeError, TypeError, ValueError, AttributeError):
            return

    def _commission_from_fingerprint(self, session: dict[str, Any]) -> bool:
        original = _safe_dict(session.get("original_fault"))
        context = _safe_dict(session.get("context"))
        pool = str(original.get("pool") or "").strip()
        member_id = str(original.get("member_id") or "").strip()
        if not pool or not member_id:
            return False

        fingerprint = self.drive_fingerprint_store.lookup(pool, member_id)
        if not isinstance(fingerprint, dict):
            return False
        if not _fingerprint_matches_session(session, fingerprint):
            return False

        try:
            bay = int(fingerprint.get("physical_bay"))
            capacity = int(fingerprint.get("capacity_bytes"))
        except (TypeError, ValueError):
            return False
        serial_last4 = str(fingerprint.get("serial_last4") or "").strip()
        source = "TruePanel last-known-good healthy drive fingerprint"
        changed = False

        physical_identity = _safe_dict(context.get("physical_identity"))
        if physical_identity:
            if not (
                physical_identity.get("verified") is True
                and str(physical_identity.get("member_id") or "").strip() == member_id
                and int(physical_identity.get("bay") or 0) == bay
                and str(physical_identity.get("serial_last4") or "").strip()
                == serial_last4
            ):
                return False
        else:
            self.lifeline_store.set_historical_physical_identity(
                str(session.get("id") or ""),
                member_id=member_id,
                bay=bay,
                serial_last4=serial_last4,
                source=source,
            )
            changed = True

        historical_media = _safe_dict(context.get("historical_media"))
        if historical_media:
            if not (
                historical_media.get("verified") is True
                and str(historical_media.get("member_id") or "").strip() == member_id
                and str(historical_media.get("serial_last4") or "").strip()
                == serial_last4
                and int(historical_media.get("capacity_bytes") or 0) == capacity
            ):
                return changed
        else:
            self.lifeline_store.set_historical_media_properties(
                str(session.get("id") or ""),
                member_id=member_id,
                serial_last4=serial_last4,
                capacity_bytes=capacity,
                model=str(fingerprint.get("model") or "").strip() or None,
                source=source,
            )
            changed = True

        return changed

    def status(self) -> dict[str, Any]:
        payload = super().status()
        try:
            self._record_healthy_fingerprints()
            result = self.lifeline_store.observe(payload)
            profile = self.lifeline_service_profile
            changed = False
            storage_devices = _safe_list(
                _safe_dict(payload.get("storage")).get("devices")
            )

            sessions = list(
                _safe_list(_safe_dict(result.get("lifeline")).get("sessions"))
            )
            for initial_session in sessions:
                if (
                    not isinstance(initial_session, dict)
                    or initial_session.get("status") != "active"
                ):
                    continue
                session_id = str(initial_session.get("id") or "")
                if not session_id:
                    continue

                session = initial_session
                if self._commission_from_fingerprint(session):
                    result = self.lifeline_store.observe(payload)
                    refreshed = _session_by_id(result, session_id)
                    if isinstance(refreshed, dict):
                        session = refreshed

                context = _safe_dict(session.get("context"))

                if profile is not None and profile.drive_service_supported:
                    if not (
                        context.get("service_procedure_verified") is True
                        and context.get("service_profile") == profile.key
                        and context.get("service_source") == profile.source_title
                    ):
                        self.lifeline_store.set_service_procedure_verified(
                            session_id,
                            verified=True,
                            profile=profile.key,
                            source=profile.source_title,
                        )
                        changed = True

                try:
                    candidates = self.replacement_candidate_provider.candidates(
                        _replacement_fault_for_session(session),
                        storage_devices=storage_devices,
                    )
                except (OSError, RuntimeError, TypeError, ValueError, AttributeError):
                    candidates = []

                existing_candidates = _safe_list(
                    context.get("replacement_candidates")
                )
                if candidates != existing_candidates:
                    self.lifeline_store.set_replacement_candidates(
                        session_id,
                        candidates,
                    )
                    changed = True

            if changed:
                result = self.lifeline_store.observe(payload)

            lifeline = dict(_safe_dict(result.get("lifeline")))
            lifeline["drive_fingerprints"] = self.drive_fingerprint_store.snapshot()
            if profile is not None:
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

        smart = [
            dict(record)
            if isinstance(record, dict)
            else record
            for record in _safe_list(state.get("smart"))
        ]
        payload["smart"] = smart
        payload["zfs_activity"] = _safe_dict(state.get("zfs_activity"))

        supplied_devices = state.get("storage_devices")
        supplied = isinstance(supplied_devices, list)
        records = supplied_devices if supplied else []
        payload["devices"] = records

        pools = _safe_list(payload.get("pools"))
        unhealthy_pool = any(
            isinstance(pool, dict)
            and str(
                pool.get("health")
                or pool.get("state")
                or ""
            ).strip().upper()
            in _UNHEALTHY_POOL_STATES
            for pool in pools
        )
        actionable_smart = any(
            _smart_requires_evidence(record)
            for record in smart
        )

        if not supplied and (unhealthy_pool or actionable_smart):
            try:
                resolved = self.storage_evidence_provider.records()
            except (OSError, RuntimeError, TypeError, ValueError, AttributeError):
                resolved = []

            if isinstance(resolved, list):
                records = resolved
                payload["devices"] = records

        if not smart or not records:
            return payload

        evidence_by_device = {}
        for record in records:
            if not isinstance(record, dict):
                continue
            if record.get("present") is False:
                continue

            device = normalize_device(record.get("device"))
            if device:
                evidence_by_device[device] = record

        enriched = []
        evidence_fields = (
            "pool",
            "vdev",
            "vdev_topology",
            "remaining_redundancy",
            "physical_bay",
            "model",
            "serial_last4",
            "zfs_state",
        )

        for record in smart:
            if not isinstance(record, dict):
                enriched.append(record)
                continue

            item = dict(record)
            device = normalize_device(
                item.get("device")
                or item.get("drive")
            )
            evidence = evidence_by_device.get(device)

            if evidence is not None:
                for key in evidence_fields:
                    value = evidence.get(key)
                    if value is not None:
                        item[key] = value

            enriched.append(item)

        payload["smart"] = enriched
        return payload


def __getattr__(name):
    """Preserve less-common module attributes from the base implementation."""

    return getattr(_base, name)


__all__ = ["SnapshotService", "get_fan_status"]
