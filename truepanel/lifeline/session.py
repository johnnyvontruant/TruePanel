"""Deterministic guided-repair sessions for Project Lifeline.

Lifeline deliberately separates *repair planning* from *repair authority*.
This module can decide which recovery phase is appropriate, validate the
observed prerequisites, and explain why a dangerous step is still locked.
It cannot offline, remove, replace, wipe, or otherwise mutate storage.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Final


DRIVE_PHASES: Final[tuple[str, ...]] = (
    "diagnose",
    "identify",
    "prepare",
    "service_ready",
    "validate_replacement",
    "replacement_ready",
    "monitor_recovery",
    "verify",
    "complete",
)

_UNHEALTHY_MEMBER_STATES = {
    "FAULTED",
    "UNAVAIL",
    "UNAVAILABLE",
    "OFFLINE",
    "REMOVED",
}
_HEALTHY_POOL_STATES = {"ONLINE"}


@dataclass(frozen=True)
class RepairGate:
    code: str
    title: str
    satisfied: bool
    detail: str
    risk: str = "safe"


@dataclass(frozen=True)
class ReplacementAssessment:
    detected: bool
    valid: bool
    device: str | None
    model: str | None
    capacity_bytes: int | None
    minimum_capacity_bytes: int | None
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class RepairSession:
    kind: str
    code: str
    phase: str
    phase_index: int
    phase_count: int
    title: str
    summary: str
    target: dict[str, Any]
    gates: tuple[RepairGate, ...]
    replacement: ReplacementAssessment
    can_identify_bay: bool
    can_begin_physical_service: bool
    can_prepare_replacement: bool
    write_preconditions_complete: bool
    can_execute_replacement: bool
    recovery_in_progress: bool
    recovery_verified: bool
    blocked_by: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _integer(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _replacement_assessment(
    *,
    failed_capacity: int | None,
    candidate: dict[str, Any] | None,
) -> ReplacementAssessment:
    candidate = candidate if isinstance(candidate, dict) else {}
    detected = bool(candidate)
    device = _text(candidate.get("device")) or None
    model = _text(candidate.get("model")) or None
    capacity = _integer(candidate.get("capacity_bytes"))
    reasons: list[str] = []

    if not detected:
        reasons.append("replacement_not_detected")
    else:
        if not device:
            reasons.append("replacement_device_not_verified")
        if capacity is None:
            reasons.append("replacement_capacity_not_verified")
        elif failed_capacity is not None and capacity < failed_capacity:
            reasons.append("replacement_capacity_too_small")
        if candidate.get("member_of_pool") is True:
            reasons.append("replacement_belongs_to_pool")
        if candidate.get("contains_preserved_data") is True:
            reasons.append("replacement_contains_preserved_data")
        if candidate.get("ambiguous") is True:
            reasons.append("replacement_identity_ambiguous")

    return ReplacementAssessment(
        detected=detected,
        valid=detected and not reasons,
        device=device,
        model=model,
        capacity_bytes=capacity,
        minimum_capacity_bytes=failed_capacity,
        reasons=tuple(reasons),
    )


def _gate(
    code: str,
    title: str,
    satisfied: bool,
    detail: str,
    *,
    risk: str = "safe",
) -> RepairGate:
    return RepairGate(
        code=code,
        title=title,
        satisfied=bool(satisfied),
        detail=detail,
        risk=risk,
    )


def evaluate_drive_repair(
    evidence: dict[str, Any],
    *,
    service_procedure_verified: bool = False,
    backup_acknowledged: bool = False,
    bay_identity_verified: bool | None = None,
    replacement_candidate: dict[str, Any] | None = None,
    replacement_operation_confirmed: bool = False,
) -> RepairSession:
    """Evaluate a drive-repair session without performing any repair action.

    Logical ZFS membership and current Linux hardware identity are deliberately
    separate. A removed disk may remain exactly identified by a ZFS member ID
    while having no current ``/dev`` node or verified physical bay.
    """

    evidence = evidence if isinstance(evidence, dict) else {}
    activity = evidence.get("resilver_state")
    activity = activity if isinstance(activity, dict) else {}

    pool = _text(evidence.get("pool"))
    vdev = _text(evidence.get("vdev"))
    topology = _text(evidence.get("vdev_topology"))
    member_id = _text(evidence.get("member_id") or evidence.get("zfs_name"))
    historical_path = _text(evidence.get("historical_path"))
    device = _text(evidence.get("device"))
    bay = evidence.get("bay") or evidence.get("physical_bay")
    state = _text(evidence.get("zfs_state")).upper()
    failed_capacity = _integer(evidence.get("capacity_bytes"))
    redundancy = evidence.get("remaining_redundancy")

    exact_member = bool(
        pool
        and vdev
        and (member_id or device)
        and state in _UNHEALTHY_MEMBER_STATES
    )
    topology_verified = bool(topology and redundancy is not None)
    physical_identity = bool(device and bay)
    if bay_identity_verified is not None:
        physical_identity = physical_identity and bool(bay_identity_verified)

    recovery_in_progress = bool(activity.get("resilver_running", False))
    pool_state = _text(evidence.get("pool_state")).upper()
    replacement_state = _text(evidence.get("replacement_zfs_state")).upper()
    recovery_candidate = bool(
        not recovery_in_progress
        and pool_state in _HEALTHY_POOL_STATES
        and replacement_state == "ONLINE"
    )
    recovery_verified = bool(
        evidence.get("recovery_verified") is True
        and recovery_candidate
    )

    replacement = _replacement_assessment(
        failed_capacity=failed_capacity,
        candidate=replacement_candidate,
    )

    gates = (
        _gate(
            "member_identity",
            "Faulted member identified",
            exact_member,
            "Pool, VDEV, logical ZFS member identity, and unhealthy member state must agree.",
        ),
        _gate(
            "redundancy",
            "VDEV redundancy understood",
            topology_verified,
            "Topology and remaining fault tolerance must be known before service planning.",
        ),
        _gate(
            "physical_identity",
            "Physical bay independently verified",
            physical_identity,
            "The hardware inventory must independently correlate a current Linux device to a physical bay.",
        ),
        _gate(
            "service_procedure",
            "Chassis service procedure verified",
            service_procedure_verified,
            "A procedure matching the detected chassis/model must be verified before physical service.",
            risk="caution",
        ),
        _gate(
            "backup_acknowledgement",
            "Backup state acknowledged",
            backup_acknowledged,
            "The operator must explicitly acknowledge the backup state before physical service proceeds.",
            risk="caution",
        ),
        _gate(
            "replacement_candidate",
            "Replacement candidate validated",
            replacement.valid,
            "The replacement must be unambiguous, large enough, and free of pool membership or data the operator intends to preserve.",
            risk="destructive",
        ),
        _gate(
            "replacement_confirmation",
            "Replacement operation explicitly confirmed",
            replacement_operation_confirmed,
            "A future write-capable implementation must require an explicit confirmation tied to the exact source and replacement devices.",
            risk="destructive",
        ),
    )

    by_code = {item.code: item.satisfied for item in gates}
    can_identify_bay = bool(exact_member and physical_identity)
    can_begin_physical_service = all(
        by_code[name]
        for name in (
            "member_identity",
            "redundancy",
            "physical_identity",
            "service_procedure",
            "backup_acknowledgement",
        )
    ) and not recovery_in_progress
    can_prepare_replacement = can_begin_physical_service and replacement.detected
    write_preconditions_complete = (
        all(item.satisfied for item in gates)
        and not recovery_in_progress
        and not recovery_candidate
    )

    can_execute_replacement = False

    if recovery_verified:
        phase = "complete"
        summary = "Recovery is verified and storage redundancy is restored."
    elif recovery_in_progress:
        phase = "monitor_recovery"
        summary = "A resilver is active. Monitor recovery and do not service another member."
    elif recovery_candidate:
        phase = "verify"
        summary = "Storage is healthy again. Continue verification before closing the repair session."
    elif not exact_member or not topology_verified:
        phase = "diagnose"
        summary = "Resolve the exact failed member and redundancy state before planning service."
    elif not physical_identity:
        phase = "identify"
        summary = "The logical fault is known, but the exact physical bay still requires independent verification."
    elif not service_procedure_verified or not backup_acknowledged:
        phase = "prepare"
        summary = "The failed bay is known. Verify the chassis procedure and acknowledge backup state before physical service."
    elif not replacement.detected:
        phase = "service_ready"
        summary = "Physical-service prerequisites are satisfied. Replacement media has not been detected yet."
    elif not replacement.valid:
        phase = "validate_replacement"
        summary = "Replacement media is present but does not yet satisfy the validation contract."
    elif not replacement_operation_confirmed:
        phase = "replacement_ready"
        summary = "Replacement media is validated. Any future storage mutation remains locked pending explicit confirmation and guarded authority."
    else:
        phase = "replacement_ready"
        summary = "All write prerequisites are satisfied, but Lifeline has no storage-write authority."

    blocked = tuple(item.code for item in gates if not item.satisfied)
    warnings: list[str] = []
    if redundancy == 0:
        warnings.append("No additional member failure can be tolerated in the affected VDEV.")
    if recovery_in_progress:
        warnings.append("Do not remove or replace another member while resilver is active.")
    if replacement.detected and not replacement.valid:
        warnings.extend(replacement.reasons)
    if write_preconditions_complete:
        warnings.append("Write prerequisites are complete, but storage execution authority is intentionally absent.")

    try:
        phase_index = DRIVE_PHASES.index(phase) + 1
    except ValueError:
        phase_index = 1

    return RepairSession(
        kind="drive_replacement",
        code="storage.disk_faulted",
        phase=phase,
        phase_index=phase_index,
        phase_count=len(DRIVE_PHASES),
        title="Guided drive recovery",
        summary=summary,
        target={
            "pool": pool or None,
            "vdev": vdev or None,
            "vdev_topology": topology or None,
            "remaining_redundancy": redundancy,
            "member_id": member_id or None,
            "historical_path": historical_path or None,
            "device": device or None,
            "bay": bay,
            "zfs_state": state or None,
            "capacity_bytes": failed_capacity,
        },
        gates=gates,
        replacement=replacement,
        can_identify_bay=can_identify_bay,
        can_begin_physical_service=can_begin_physical_service,
        can_prepare_replacement=can_prepare_replacement,
        write_preconditions_complete=write_preconditions_complete,
        can_execute_replacement=can_execute_replacement,
        recovery_in_progress=recovery_in_progress,
        recovery_verified=recovery_verified,
        blocked_by=blocked,
        warnings=tuple(warnings),
    )


__all__ = [
    "DRIVE_PHASES",
    "RepairGate",
    "RepairSession",
    "ReplacementAssessment",
    "evaluate_drive_repair",
]
