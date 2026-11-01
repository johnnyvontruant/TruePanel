"""Incident-bound, advisory storage recovery plans for Project CHECKRIDE.

CHECKRIDE composes evidence already collected by AEGIS and Lifeline.  It has no
storage or hardware authority: every physical step remains gated on operator
confirmation and fresh passive identity checks.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime
from typing import Any

from .attestations import (
    BACKUP_KIND,
    CANDIDATE_KIND,
    collect_recovery_attestations,
    reconcile_recovery_attestations,
)

_CLEARANCE_MAX_AGE_SECONDS = 15 * 60


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _timestamp(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = _text(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _fresh(observed_at: Any, now: float | None) -> tuple[bool, float | None]:
    observed = _timestamp(observed_at)
    if observed is None or now is None:
        return False, None
    age = max(0.0, now - observed)
    return age <= _CLEARANCE_MAX_AGE_SECONDS, age


def _selected_candidate(context: dict[str, Any]) -> dict[str, Any]:
    candidates = [
        item
        for item in _list(context.get("replacement_candidates"))
        if isinstance(item, dict)
    ]
    selected = [item for item in candidates if item.get("selected") is True]
    if len(selected) == 1:
        return selected[0]
    if len(selected) == 0 and len(candidates) == 1:
        return candidates[0]
    return {}


def _matching_lifeline_session(
    payload: dict[str, Any],
    identity: dict[str, Any],
) -> dict[str, Any]:
    sessions = _list(_dict(payload.get("lifeline")).get("sessions"))
    for session in sessions:
        if not isinstance(session, dict) or session.get("status") != "active":
            continue
        original = _dict(session.get("original_fault"))
        compared = ("pool", "vdev", "device", "bay", "serial_last4")
        if all(
            original.get(field) is None
            or identity.get(field) is None
            or str(original.get(field)) == str(identity.get(field))
            for field in compared
        ) and any(original.get(field) is not None for field in compared):
            return session
    return {}


def evaluate_pre_service_clearance(
    payload: dict[str, Any],
    *,
    incident_id: str,
    identity: dict[str, Any],
    topology: dict[str, Any],
) -> dict[str, Any]:
    """Compose a digest-bound, advisory-only physical-service clearance.

    ``READY_FOR_OPERATOR_REVIEW`` never means that TruePanel may mutate
    storage. It means only that the passive evidence needed for a human to
    review the external service procedure is mutually consistent and fresh.
    """

    now = _timestamp(payload.get("timestamp"))
    snapshot_fresh, snapshot_age = _fresh(payload.get("timestamp"), now)
    session = _matching_lifeline_session(payload, identity)
    context = _dict(session.get("context"))
    last_session = _dict(session.get("last_session"))
    candidate = _selected_candidate(context)
    replacement = _dict(last_session.get("replacement"))
    backup = _dict(payload.get("backup_context"))

    session_fresh, session_age = _fresh(session.get("updated_at"), now)
    backup_fresh, backup_age = _fresh(backup.get("verified_at"), now)
    candidate_fresh, candidate_age = _fresh(
        candidate.get("observed_at", session.get("updated_at")),
        now,
    )

    complete_identity = identity.get("verified_from_passive_evidence") is True
    attestations = collect_recovery_attestations(
        payload,
        incident_id=incident_id,
        source_identity_sha256=_text(identity.get("identity_sha256")) or None,
    )
    evidence_ledger = reconcile_recovery_attestations(
        attestations,
        incident_id=incident_id,
        now=now,
    )
    accepted_kinds = {
        item.get("kind") for item in _list(evidence_ledger.get("accepted"))
    }
    redundancy = topology.get("remaining_redundancy")
    safe_margin = (
        topology.get("vdev_topology") is not None
        and isinstance(redundancy, int)
        and not isinstance(redundancy, bool)
        and redundancy > 0
        and _text(topology.get("zfs_state")).upper() in {"ONLINE", "DEGRADED"}
    )
    backup_proven = bool(
        backup.get("independent_backup_confirmed") is True
        and backup.get("restore_tested") is True
        and _text(backup.get("source"))
        and backup_fresh
        and BACKUP_KIND in accepted_kinds
    )
    distinct_candidate = bool(
        candidate.get("identity_verified_distinct") is True
        or (
            _text(candidate.get("serial_last4"))
            and _text(candidate.get("serial_last4"))
            != _text(identity.get("serial_last4"))
        )
    )
    replacement_valid = bool(
        session_fresh
        and candidate_fresh
        and replacement.get("valid") is True
        and distinct_candidate
        and CANDIDATE_KIND in accepted_kinds
    )
    service_procedure = bool(
        context.get("service_procedure_verified") is True
        and _text(context.get("service_profile"))
        and _text(context.get("service_source"))
    )
    zfs_activity = _dict(_dict(payload.get("storage")).get("zfs_activity"))
    no_recovery_active = zfs_activity.get("resilver_running") is not True

    gates = [
        {
            "code": "incident_identity",
            "satisfied": bool(incident_id and complete_identity and snapshot_fresh),
            "evidence_age_seconds": snapshot_age,
            "detail": "Incident, bay, device, model, serial suffix, pool, and VDEV must be present in the current passive snapshot.",
        },
        {
            "code": "redundancy_margin",
            "satisfied": safe_margin,
            "evidence_age_seconds": snapshot_age,
            "detail": "Current topology must retain at least one additional member of fault tolerance.",
        },
        {
            "code": "backup_restore_evidence",
            "satisfied": backup_proven,
            "evidence_age_seconds": backup_age,
            "detail": "An independent backup with a tested restore and named source must be attested within 15 minutes.",
        },
        {
            "code": "service_procedure",
            "satisfied": service_procedure,
            "evidence_age_seconds": session_age,
            "detail": "The service procedure must match a known chassis profile and retain its source provenance.",
        },
        {
            "code": "replacement_fit_and_identity",
            "satisfied": replacement_valid,
            "evidence_age_seconds": candidate_age,
            "detail": "One fresh, distinct, equal-or-larger candidate must be outside every pool and free of preserved-data risk.",
        },
        {
            "code": "recovery_quiescent",
            "satisfied": no_recovery_active,
            "evidence_age_seconds": snapshot_age,
            "detail": "No resilver may be active while a physical-service plan is reviewed.",
        },
        {
            "code": "provider_attestation_integrity",
            "satisfied": evidence_ledger["status"] == "EVIDENCE_READY",
            "evidence_age_seconds": snapshot_age,
            "detail": "Backup and candidate evidence must be fresh, incident-bound, digest-intact, independently sourced, and free of contradictions.",
        },
    ]
    blocked_by = [item["code"] for item in gates if item["satisfied"] is not True]
    status = "READY_FOR_OPERATOR_REVIEW" if not blocked_by else "HOLD"
    receipt = {
        "schema_version": 1,
        "incident_id": incident_id,
        "status": status,
        "generated_at": payload.get("timestamp"),
        "expires_after_seconds": _CLEARANCE_MAX_AGE_SECONDS,
        "gates": gates,
        "source_identity": {
            field: identity.get(field)
            for field in ("pool", "vdev", "bay", "device", "model", "serial_last4")
        },
        "replacement_identity": {
            field: candidate.get(field)
            for field in ("device", "bay", "model", "serial_last4", "capacity_bytes")
        },
        "backup_evidence": {
            "source": backup.get("source"),
            "verified_at": backup.get("verified_at"),
            "restore_tested": backup.get("restore_tested") is True,
        },
        "evidence_ledger": evidence_ledger,
        "blocked_by": blocked_by,
        "operator_review_ready": not blocked_by,
        "physical_service_authority": False,
        "storage_write_authority": False,
    }
    canonical = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
    receipt["receipt_sha256"] = hashlib.sha256(canonical).hexdigest()
    return receipt


def _storage_evidence(incident: dict[str, Any]) -> dict[str, Any] | None:
    for signal in _list(incident.get("supporting_signals")):
        if not isinstance(signal, dict):
            continue
        if signal.get("signal") not in {
            "storage.smart_warning",
            "storage.disk_faulted",
        }:
            continue
        evidence = _dict(signal.get("evidence"))
        if evidence:
            return deepcopy(evidence)
    return None


def run_storage_recovery_rehearsals() -> list[dict[str, Any]]:
    """Return deterministic, hardware-isolated recovery branch results."""

    return [
        {
            "choice": "correct_identity_and_fit",
            "outcome": "proceed_to_operator_review",
            "hardware_isolated": True,
            "reason": "Identity, capacity, pool non-membership, backup, and redundancy gates all pass.",
        },
        {
            "choice": "wrong_bay_or_serial",
            "outcome": "abort",
            "hardware_isolated": True,
            "reason": "Fresh bay and serial evidence does not match the incident identity.",
        },
        {
            "choice": "replacement_undersized_or_in_use",
            "outcome": "abort",
            "hardware_isolated": True,
            "reason": "Candidate capacity is insufficient or the disk belongs to another pool.",
        },
        {
            "choice": "pool_degraded_or_backup_unconfirmed",
            "outcome": "hold",
            "hardware_isolated": True,
            "reason": "The safety margin is not independently established.",
        },
        {
            "choice": "resilver_progressing",
            "outcome": "observe",
            "hardware_isolated": True,
            "reason": "Keep the workload conservative and verify progress and error counters.",
        },
        {
            "choice": "resilver_stalled_or_new_errors",
            "outcome": "hold_and_escalate",
            "hardware_isolated": True,
            "reason": "Do not claim recovery while progress stalls or new errors accumulate.",
        },
    ]


def compose_storage_checkride(
    payload: dict[str, Any],
    incident: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Compose a live-scoped storage plan from verified incident evidence."""

    active = _dict(incident)
    incident_id = _text(active.get("incident_id"))
    evidence = _storage_evidence(active)
    if not incident_id or evidence is None:
        return None

    identity_fields = ("pool", "vdev", "bay", "device", "model", "serial_last4")
    missing_identity = [field for field in identity_fields if not evidence.get(field)]
    identity = {field: evidence.get(field) for field in identity_fields}
    identity["identity_sha256"] = evidence.get("identity_sha256")
    identity["verified_from_passive_evidence"] = not missing_identity
    identity["missing"] = missing_identity

    topology = {
        "pool": evidence.get("pool"),
        "vdev": evidence.get("vdev"),
        "vdev_topology": evidence.get("vdev_topology"),
        "remaining_redundancy": evidence.get("remaining_redundancy"),
        "zfs_state": evidence.get("zfs_state"),
    }
    missing_topology = [
        field
        for field in ("vdev_topology", "remaining_redundancy", "zfs_state")
        if topology.get(field) is None
    ]

    storage = _dict(payload.get("storage"))
    activity = _dict(storage.get("zfs_activity"))
    backup = _dict(payload.get("backup_context"))
    backup_confirmed = backup.get("independent_backup_confirmed") is True
    blockers = []
    if missing_identity:
        blockers.append("physical_and_logical_identity_incomplete")
    if missing_topology:
        blockers.append("redundancy_context_incomplete")
    if not backup_confirmed:
        blockers.append("independent_backup_not_confirmed_in_telemetry")
    blockers.append("replacement_candidate_not_verified")
    blockers.append("fresh_pre_service_identity_check_required")

    bay = evidence.get("bay") or "unknown"
    device = _text(evidence.get("device")) or "unknown device"
    serial = _text(evidence.get("serial_last4")) or "unknown"
    plan = {
        "schema_version": 1,
        "project": "CHECKRIDE",
        "domain": "storage",
        "scenario": "storage-smart-recovery-v1",
        "presentation_scope": "active_incident",
        "incident_id": incident_id,
        "applies_to_active_incident": True,
        "simulation": False,
        "field_validated": False,
        "evidence_maturity": "passive_live_diagnosis_repair_unvalidated",
        "control_authority": False,
        "identity": identity,
        "topology": topology,
        "topology_gaps": missing_topology,
        "backup_context": {
            "independent_backup_confirmed": backup_confirmed,
            "source": backup.get("source") or "operator confirmation required",
        },
        "resilver": {
            "running": activity.get("resilver_running") is True,
            "percent": activity.get("percent"),
            "problem": activity.get("problem") is True,
        },
        "safest_action": (
            f"Keep bay {bay} ({device}, serial suffix {serial}) installed. "
            "Confirm the independent backup and obtain an equal-or-larger replacement; "
            "repeat identity and redundancy checks immediately before service."
        ),
        "action_gate": {
            "physical_service_ready": False,
            "destructive_actions_ready": False,
            "blocked_by": blockers,
        },
        "abort_conditions": [
            "Bay, serial suffix, device, pool, or VDEV identity does not match fresh evidence.",
            "Independent backup health is not confirmed.",
            "Pool state or remaining redundancy is worse than the reviewed plan.",
            "Replacement is smaller, already belongs to a pool, or has ambiguous identity.",
            "Resilver stalls, reports a problem, or new read/write/checksum errors accumulate.",
        ],
        "expected_recovery_observations": [
            "The replacement has the reviewed new identity in the intended bay and VDEV.",
            "Resilver begins, advances monotonically, and reports no new problem evidence.",
            "The pool returns to ONLINE with the intended topology.",
            "The original SMART incident is absent for the reviewed observation window.",
        ],
        "verification_signature": {
            "status": "awaiting_external_repair",
            "machine_verifiable": True,
            "criteria": {
                "replacement_identity_changed": True,
                "intended_pool_and_vdev_match": True,
                "resilver_completed_without_problem": True,
                "pool_state": "ONLINE",
                "triggering_smart_incident_absent": True,
            },
        },
        "rehearsals": run_storage_recovery_rehearsals(),
        "evidence": evidence,
        "read_only": True,
        "provenance": {
            "systems": ["AEGIS", "ORACLE", "Lifeline", "Pathfinder", "HoloDeck"],
            "claim": "Live passive diagnosis; repair outcome not yet observed.",
        },
    }
    plan["pre_service_clearance"] = evaluate_pre_service_clearance(
        payload,
        incident_id=incident_id,
        identity=identity,
        topology=topology,
    )
    plan["action_gate"]["operator_review_ready"] = plan[
        "pre_service_clearance"
    ]["operator_review_ready"]
    structural_blockers = [
        item
        for item in blockers
        if item
        in {
            "physical_and_logical_identity_incomplete",
            "redundancy_context_incomplete",
        }
    ]
    plan["action_gate"]["blocked_by"] = list(
        dict.fromkeys(
            structural_blockers
            + plan["pre_service_clearance"]["blocked_by"]
        )
    )
    canonical = json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
    plan["evidence_sha256"] = hashlib.sha256(canonical).hexdigest()
    return plan


__all__ = [
    "compose_storage_checkride",
    "evaluate_pre_service_clearance",
    "run_storage_recovery_rehearsals",
]
