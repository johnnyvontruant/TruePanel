"""Critical-SMART pre-failure handoff for Project Lifeline.

This extension preserves the established ZFS-fault repair contract while
allowing replacement-worthy SMART evidence to open a metadata-only Lifeline
session before ZFS marks the member unhealthy.  It adds no storage mutation
authority.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .store import LifelineSessionStore as _BaseLifelineSessionStore


_DISK_FAULT_CODE = "storage.disk_faulted"
_SMART_WARNING_CODE = "storage.smart_warning"
_REQUIRED_HEALTHY_OBSERVATIONS = 3


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _fault_key(evidence: dict[str, Any]) -> str | None:
    pool = _text(evidence.get("pool"))
    vdev = _text(evidence.get("vdev"))
    device = _text(evidence.get("device"))
    member_id = _text(evidence.get("member_id") or evidence.get("zfs_name"))
    identity = device or member_id
    if not pool or not vdev or not identity:
        return None
    return f"drive:{pool}:{vdev}:{identity}"


def _pool_state(payload: dict[str, Any], pool_name: str) -> str:
    storage = _dict(payload.get("storage"))
    for pool in _list(storage.get("pools")):
        if not isinstance(pool, dict):
            continue
        if _text(pool.get("name")) != pool_name:
            continue
        return _text(pool.get("health") or pool.get("state")).upper()
    return ""


def _resilver_running(payload: dict[str, Any]) -> bool:
    storage = _dict(payload.get("storage"))
    activity = _dict(storage.get("zfs_activity"))
    return bool(activity.get("resilver_running", False))


def _critical_smart_evidence(evidence: dict[str, Any]) -> bool:
    health = _text(evidence.get("smart_health") or evidence.get("health")).upper()
    warning = _text(evidence.get("critical_warning")).lower()
    return bool(
        health == "FAILED"
        or _integer(evidence.get("pending")) > 0
        or _integer(evidence.get("offline_uncorrectable")) > 0
        or _integer(evidence.get("media_errors")) > 0
        or warning not in {"", "0", "0x0", "0x00"}
    )


def _is_critical_smart_card(
    item: dict[str, Any],
    evidence: dict[str, Any],
) -> bool:
    runtime = _dict(item.get("runtime"))
    return bool(
        item.get("code") == _SMART_WARNING_CODE
        and _text(item.get("severity")).lower() == "critical"
        and _text(runtime.get("disposition")) == "prepare_replacement"
        and _critical_smart_evidence(evidence)
    )


def _device_evidence(
    payload: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """Fill SMART guidance gaps only from one exact storage-device match."""

    merged = dict(evidence)
    storage = _dict(payload.get("storage"))
    target_device = _text(evidence.get("device"))
    target_pool = _text(evidence.get("pool"))
    target_vdev = _text(evidence.get("vdev"))

    matches: list[dict[str, Any]] = []
    for record in _list(storage.get("devices")):
        if not isinstance(record, dict):
            continue
        record_device = _text(record.get("device") or record.get("drive"))
        if not target_device or record_device != target_device:
            continue
        record_pool = _text(record.get("pool"))
        record_vdev = _text(record.get("vdev"))
        if target_pool and record_pool and record_pool != target_pool:
            continue
        if target_vdev and record_vdev and record_vdev != target_vdev:
            continue
        matches.append(record)

    if len(matches) != 1:
        return merged

    record = matches[0]
    aliases = {
        "member_id": ("member_id", "zfs_name"),
        "historical_path": ("historical_path",),
        "vdev_topology": ("vdev_topology",),
        "remaining_redundancy": ("remaining_redundancy",),
        "bay": ("bay", "physical_bay"),
        "model": ("model",),
        "serial_last4": ("serial_last4",),
        "capacity_bytes": ("capacity_bytes",),
        "zfs_state": ("zfs_state", "state"),
    }
    for destination, sources in aliases.items():
        if merged.get(destination) not in (None, ""):
            continue
        for source in sources:
            value = record.get(source)
            if value not in (None, ""):
                merged[destination] = value
                break

    pool_name = _text(merged.get("pool"))
    if pool_name and not _text(merged.get("pool_state")):
        merged["pool_state"] = _pool_state(payload, pool_name)
    return merged


def _same_target(
    evidence: dict[str, Any],
    original: dict[str, Any],
) -> bool:
    pool = _text(original.get("pool"))
    vdev = _text(original.get("vdev"))
    if pool and _text(evidence.get("pool")) != pool:
        return False
    if vdev and _text(evidence.get("vdev")) != vdev:
        return False

    original_bay = original.get("bay")
    evidence_bay = evidence.get("bay") or evidence.get("physical_bay")
    if original_bay is not None and evidence_bay is not None:
        try:
            return int(original_bay) == int(evidence_bay)
        except (TypeError, ValueError):
            return False

    original_device = _text(original.get("device"))
    return bool(
        original_device
        and _text(evidence.get("device") or evidence.get("drive"))
        == original_device
    )


def _smart_warning_present(
    guidance: list[Any],
    original: dict[str, Any],
) -> bool:
    for item in guidance:
        if not isinstance(item, dict) or item.get("code") != _SMART_WARNING_CODE:
            continue
        evidence = _dict(_dict(item.get("runtime")).get("evidence"))
        if _same_target(evidence, original):
            return True
    return False


def _replacement_identity_observed(
    payload: dict[str, Any],
    original: dict[str, Any],
) -> bool:
    """Require a new serial suffix in the exact original bay, fail closed."""

    pool = _text(original.get("pool"))
    original_serial = _text(original.get("serial_last4"))
    original_bay = original.get("bay")
    if not pool or not original_serial or original_bay is None:
        return False

    storage = _dict(payload.get("storage"))
    matches: list[dict[str, Any]] = []
    for record in _list(storage.get("smart")):
        if not isinstance(record, dict):
            continue
        if _text(record.get("pool")) != pool:
            continue
        bay = record.get("bay") or record.get("physical_bay")
        try:
            same_bay = int(bay) == int(original_bay)
        except (TypeError, ValueError):
            same_bay = False
        if same_bay:
            matches.append(record)

    if len(matches) != 1:
        return False

    record = matches[0]
    state = _text(record.get("zfs_state") or record.get("state")).upper()
    replacement_serial = _text(record.get("serial_last4"))
    warning = _text(record.get("critical_warning")).lower()
    smart_clean = bool(
        _text(record.get("health")).upper() != "FAILED"
        and _integer(record.get("reallocated")) == 0
        and _integer(record.get("pending")) == 0
        and _integer(record.get("offline_uncorrectable")) == 0
        and _integer(record.get("reported_uncorrect")) == 0
        and _integer(record.get("media_errors")) == 0
        and warning in {"", "0", "0x0", "0x00"}
    )
    return bool(
        state == "ONLINE"
        and smart_clean
        and replacement_serial
        and replacement_serial != original_serial
    )


class LifelineSessionStore(_BaseLifelineSessionStore):
    """Add a fail-closed critical-SMART route beside the ZFS-fault route."""

    def _new_smart_session(
        self,
        key: str,
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        ledger = super()._new_session(key, evidence)
        ledger["trigger_code"] = _SMART_WARNING_CODE
        ledger["trigger_kind"] = "critical_smart_prefailure"
        ledger["original_fault"]["zfs_state"] = evidence.get("zfs_state")
        ledger["trigger"] = {
            "severity": "critical",
            "disposition": "prepare_replacement",
        }
        return ledger

    @staticmethod
    def _trigger_code(ledger: dict[str, Any]) -> str:
        return _text(ledger.get("trigger_code")) or _DISK_FAULT_CODE

    def _evaluate(
        self,
        ledger: dict[str, Any],
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        if self._trigger_code(ledger) != _SMART_WARNING_CODE:
            return super()._evaluate(ledger, evidence)

        actual_state = _text(evidence.get("zfs_state")).upper() or "ONLINE"
        evaluation_evidence = dict(evidence)
        if actual_state == "ONLINE":
            # The base evaluator correctly requires an unhealthy ZFS state.
            # For this isolated pre-failure route, independently verified
            # critical SMART evidence is the equivalent member-health gate.
            evaluation_evidence["zfs_state"] = "FAULTED"

        repair = super()._evaluate(ledger, evaluation_evidence)
        repair["code"] = _SMART_WARNING_CODE
        repair["title"] = "Guided pre-failure drive recovery"
        repair["summary"] = (
            _text(repair.get("summary"))
            .replace("failed bay", "at-risk bay")
            .replace("failed member", "at-risk member")
        )

        target = _dict(repair.get("target"))
        target["zfs_state"] = actual_state
        target["trigger"] = "critical_smart_prefailure"
        repair["target"] = target

        for gate in _list(repair.get("gates")):
            if not isinstance(gate, dict) or gate.get("code") != "member_identity":
                continue
            gate["title"] = "At-risk member identified"
            gate["detail"] = (
                "Pool, VDEV, exact member identity, and replacement-worthy "
                "critical SMART evidence must agree."
            )
        return repair

    def _prefailure_completion_ready(
        self,
        payload: dict[str, Any],
        guidance: list[Any],
        ledger: dict[str, Any],
    ) -> bool:
        original = _dict(ledger.get("original_fault"))
        context = _dict(ledger.get("context"))
        acknowledgements = _dict(context.get("acknowledgements"))
        last_session = _dict(ledger.get("last_session"))
        replacement = _dict(last_session.get("replacement"))

        return bool(
            context.get("service_procedure_verified") is True
            and acknowledgements.get("backup_state") is True
            and replacement.get("valid") is True
            and not _smart_warning_present(guidance, original)
            and _replacement_identity_observed(payload, original)
        )

    def observe(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = deepcopy(payload)
        guidance = _list(result.get("operator_guidance"))
        now = float(self.clock())
        changed = False
        seen_faults: set[str] = set()

        with self._lock:
            sessions = self._state["sessions"]

            for item in guidance:
                if not isinstance(item, dict):
                    continue
                code = _text(item.get("code"))
                runtime = _dict(item.get("runtime"))
                evidence = _dict(runtime.get("evidence"))

                is_disk_fault = code == _DISK_FAULT_CODE
                is_smart_fault = _is_critical_smart_card(item, evidence)
                if not is_disk_fault and not is_smart_fault:
                    continue

                if is_smart_fault:
                    evidence = _device_evidence(result, evidence)

                key = _fault_key(evidence)
                if key is None:
                    continue

                seen_faults.add(key)
                ledger = self._active_for_fault(key)
                if ledger is None:
                    if is_smart_fault:
                        ledger = self._new_smart_session(key, evidence)
                    else:
                        ledger = super()._new_session(key, evidence)
                    changed = True
                elif (
                    is_disk_fault
                    and self._trigger_code(ledger) == _SMART_WARNING_CODE
                ):
                    # ZFS has now confirmed the fault. Escalate to the original,
                    # stricter ZFS-fault contract and never downgrade later.
                    ledger["trigger_code"] = _DISK_FAULT_CODE
                    ledger["trigger_kind"] = "zfs_fault"
                    changed = True
                elif is_smart_fault and self._trigger_code(ledger) == _DISK_FAULT_CODE:
                    # An established ZFS fault remains authoritative.
                    continue

                if ledger.get("healthy_observations") != 0:
                    ledger["healthy_observations"] = 0
                    changed = True
                ledger["updated_at"] = now
                repair = self._evaluate(ledger, evidence)
                if ledger.get("last_session") != repair:
                    ledger["last_session"] = repair
                    changed = True
                item["repair_session"] = deepcopy(repair)

            for ledger in list(sessions.values()):
                if not isinstance(ledger, dict) or ledger.get("status") != "active":
                    continue
                if ledger.get("fault_key") in seen_faults:
                    continue

                original = _dict(ledger.get("original_fault"))
                pool_name = _text(original.get("pool"))
                pool_state = _pool_state(result, pool_name)
                resilver = _resilver_running(result)
                trigger_code = self._trigger_code(ledger)

                healthy_base = pool_state == "ONLINE" and not resilver
                if trigger_code == _SMART_WARNING_CODE:
                    healthy_ready = bool(
                        healthy_base
                        and self._prefailure_completion_ready(
                            result,
                            guidance,
                            ledger,
                        )
                    )
                else:
                    healthy_ready = healthy_base

                if healthy_ready:
                    healthy = int(ledger.get("healthy_observations", 0)) + 1
                    ledger["healthy_observations"] = healthy
                    changed = True
                    evidence = dict(original)
                    evidence.update(
                        {
                            "pool_state": "ONLINE",
                            "replacement_zfs_state": "ONLINE",
                            "recovery_verified": (
                                healthy >= _REQUIRED_HEALTHY_OBSERVATIONS
                            ),
                            "resilver_state": {
                                "resilver_running": False,
                            },
                        }
                    )
                    repair = self._evaluate(ledger, evidence)
                    ledger["last_session"] = repair
                    ledger["updated_at"] = now
                    if healthy >= _REQUIRED_HEALTHY_OBSERVATIONS:
                        ledger["status"] = "completed"
                        ledger["completed_at"] = now
                else:
                    if ledger.get("healthy_observations") != 0:
                        ledger["healthy_observations"] = 0
                        changed = True
                    ledger["updated_at"] = now

            if changed:
                self._save()

            result["lifeline"] = self.snapshot()
            return result


__all__ = ["LifelineSessionStore"]
