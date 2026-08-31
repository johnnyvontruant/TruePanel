"""Incident-bound, advisory storage recovery plans for Project CHECKRIDE.

CHECKRIDE composes evidence already collected by AEGIS and Lifeline.  It has no
storage or hardware authority: every physical step remains gated on operator
confirmation and fresh passive identity checks.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


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
    canonical = json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
    plan["evidence_sha256"] = hashlib.sha256(canonical).hexdigest()
    return plan


__all__ = ["compose_storage_checkride", "run_storage_recovery_rehearsals"]
