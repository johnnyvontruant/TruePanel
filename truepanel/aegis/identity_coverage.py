"""Candidate identity-continuity contract for storage recovery coverage.

This module deliberately does not modify the accepted v1 Recovery Coverage
Matrix.  It builds a separately rehearsed candidate that must be promoted by
the existing independent airworthiness-review workflow.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

IDENTITY_REQUIRED_CODES = (
    "storage.smart_warning",
    "storage.disk_faulted",
    "storage.pool_degraded",
)
ACCEPTED_IDENTITY_MODES = ("serial_model", "zfs_member", "wwn")
_STRENGTH = {"serial_model": 3, "zfs_member": 3, "wwn": 4}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _identity(session: Mapping[str, Any]) -> dict[str, Any]:
    return _dict(session.get("drive_identity"))


def _trusted_identity(identity: Mapping[str, Any]) -> bool:
    mode = str(identity.get("mode") or "")
    confidence = str(identity.get("confidence") or "")
    key = str(identity.get("stable_key") or "")
    expected_prefix = "serial:" if mode == "serial_model" else f"{mode}:"
    return (
        mode in ACCEPTED_IDENTITY_MODES
        and confidence in {"high", "very_high"}
        and key.startswith(expected_prefix)
        and len(key) > len(expected_prefix)
        and identity.get("raw_serial_exposed") is False
        and identity.get("raw_wwn_exposed") is False
    )


def _scope(session: Mapping[str, Any]) -> tuple[str, str]:
    original = _dict(session.get("original_fault"))
    return str(original.get("pool") or ""), str(original.get("vdev") or "")


def evaluate_identity_handoff(
    before_session: Mapping[str, Any],
    after_session: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify an identity upgrade or stable observation without exposing IDs."""

    before = _dict(dict(before_session))
    after = _dict(dict(after_session))
    before_identity = _identity(before)
    after_identity = _identity(after)
    before_mode = str(before_identity.get("mode") or "unknown")
    after_mode = str(after_identity.get("mode") or "unknown")
    holds: list[str] = []

    if before.get("status") != "active" or after.get("status") != "active":
        holds.append("both observations must describe the active recovery session")
    if not _trusted_identity(before_identity) or not _trusted_identity(after_identity):
        holds.append("strong privacy-safe identity evidence is required")
    if not all(_scope(before)) or _scope(before) != _scope(after):
        holds.append("pool and VDEV recovery scope must remain exact")

    before_key = str(before_identity.get("stable_key") or "")
    after_key = str(after_identity.get("stable_key") or "")
    continuity = "STABLE" if before_key and before_key == after_key else "MIGRATED"
    if continuity == "MIGRATED":
        if _STRENGTH.get(after_mode, -1) <= _STRENGTH.get(before_mode, -1):
            holds.append("identity changes require a strictly stronger successor")
        if str(before.get("id") or "") not in _list(after.get("legacy_ids")):
            holds.append("predecessor session ID is missing from migration lineage")
        if str(before.get("fault_key") or "") not in _list(
            after.get("legacy_fault_keys")
        ):
            holds.append("predecessor fault key is missing from migration lineage")

    history = {str(item) for item in _list(after.get("device_history")) if item}
    for device in (before.get("current_device"), after.get("current_device")):
        if device and str(device) not in history:
            holds.append("device-path history does not cover both observations")
            break

    return {
        "status": "HOLD" if holds else "TRUSTED",
        "continuity": continuity,
        "before_mode": before_mode,
        "after_mode": after_mode,
        "scope_preserved": bool(
            all(_scope(before)) and _scope(before) == _scope(after)
        ),
        "privacy_safe": bool(
            _trusted_identity(before_identity) and _trusted_identity(after_identity)
        ),
        "holds": holds,
    }


def evaluate_identity_uniqueness(
    sessions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Reject cloned stable identities and reused runtime paths."""

    active = [item for item in sessions if item.get("status") == "active"]
    keys: dict[str, int] = {}
    paths: dict[str, set[str]] = {}
    holds: list[str] = []
    for session in active:
        identity = _identity(session)
        if not _trusted_identity(identity):
            holds.append("every active storage recovery requires strong identity")
            continue
        key = str(identity.get("stable_key"))
        keys[key] = keys.get(key, 0) + 1
        for path in _list(session.get("device_history")) + [
            session.get("current_device")
        ]:
            if path:
                paths.setdefault(str(path), set()).add(key)
    if any(count > 1 for count in keys.values()):
        holds.append("one stable identity is active in multiple recovery sessions")
    if any(len(owners) > 1 for owners in paths.values()):
        holds.append("one runtime device path maps to multiple stable identities")
    return {
        "status": "HOLD" if holds else "TRUSTED",
        "active_sessions": len(active),
        "unique_identities": len(keys),
        "holds": holds,
    }


def rehearse_identity_coverage_contract() -> dict[str, Any]:
    """Run deterministic, synthetic candidate-contract challenge cases."""

    def session(mode: str, key: str, device: str) -> dict[str, Any]:
        return {
            "id": f"session-{mode}",
            "fault_key": f"fault-{mode}",
            "status": "active",
            "current_device": device,
            "device_history": [device],
            "original_fault": {"pool": "tank", "vdev": "raidz1-0"},
            "drive_identity": {
                "mode": mode,
                "confidence": "very_high" if mode == "wwn" else "high",
                "stable_key": key,
                "raw_serial_exposed": False,
                "raw_wwn_exposed": False,
            },
        }

    before = session("serial_model", "serial:opaque-a", "sdc")
    after = session("wwn", "wwn:opaque-b", "sda")
    after["legacy_ids"] = [before["id"]]
    after["legacy_fault_keys"] = [before["fault_key"]]
    after["device_history"] = ["sdc", "sda"]
    stable = session("wwn", "wwn:opaque-b", "sda")
    missing_lineage = deepcopy(after)
    missing_lineage["legacy_ids"] = []
    clone = deepcopy(stable)
    clone["id"] = "session-clone"
    reused = session("wwn", "wwn:opaque-c", "sda")
    scenarios = [
        {
            "name": "serial-to-wwn",
            "expected": "TRUSTED",
            "result": evaluate_identity_handoff(before, after),
        },
        {
            "name": "stable-wwn",
            "expected": "TRUSTED",
            "result": evaluate_identity_handoff(stable, stable),
        },
        {
            "name": "missing-lineage",
            "expected": "HOLD",
            "result": evaluate_identity_handoff(before, missing_lineage),
        },
        {
            "name": "cloned-identity",
            "expected": "HOLD",
            "result": evaluate_identity_uniqueness([stable, clone]),
        },
        {
            "name": "reused-path",
            "expected": "HOLD",
            "result": evaluate_identity_uniqueness([stable, reused]),
        },
    ]
    false_outcomes = sum(
        item["result"]["status"] != item["expected"] for item in scenarios
    )
    report = {
        "schema": "truepanel.aegis-identity-coverage-rehearsal/v1",
        "simulation": True,
        "production_mutation": False,
        "control_authority": False,
        "status": "passed" if false_outcomes == 0 else "failed",
        "measurements": {
            "scenarios": len(scenarios),
            "trusted": sum(item["expected"] == "TRUSTED" for item in scenarios),
            "holds": sum(item["expected"] == "HOLD" for item in scenarios),
            "false_outcomes": false_outcomes,
            "raw_identifiers_retained": 0,
        },
        "scenarios": scenarios,
    }
    report["evidence_sha256"] = _canonical_sha256(report)
    return report


def build_identity_coverage_candidate(
    accepted_matrix: Mapping[str, Any], rehearsal: Mapping[str, Any]
) -> dict[str, Any]:
    """Extend accepted coverage as an unaccepted, content-bound candidate."""

    accepted = deepcopy(dict(accepted_matrix))
    candidate_entries = deepcopy(_list(accepted.get("entries")))
    evidence = deepcopy(dict(rehearsal))
    for entry in candidate_entries:
        code = str(entry.get("code") or "")
        required = code in IDENTITY_REQUIRED_CODES
        entry["identity_continuity"] = {
            "required": required,
            "accepted_modes": list(ACCEPTED_IDENTITY_MODES) if required else [],
            "regression_scenario": "aegis-stable-identity-migration"
            if required
            else None,
            "rehearsal_status": evidence.get("status") if required else "not_required",
        }
    candidate = {
        "schema": "truepanel.aegis-recovery-coverage/v2-candidate",
        "schema_version": 2,
        "read_only": True,
        "accepted": False,
        "automatic_acceptance": False,
        "review_required": True,
        "predecessor_sha256": _canonical_sha256(accepted),
        "total": accepted.get("total"),
        "trusted": accepted.get("trusted"),
        "gaps": accepted.get("gaps"),
        "identity_required_codes": list(IDENTITY_REQUIRED_CODES),
        "identity_rehearsal": evidence,
        "entries": candidate_entries,
    }
    errors = validate_identity_coverage_candidate(candidate)
    candidate["contract_errors"] = list(errors)
    candidate["status"] = (
        "READY_FOR_OPERATOR_REVIEW"
        if not errors and evidence.get("status") == "passed"
        else "HOLD"
    )
    candidate["candidate_sha256"] = _canonical_sha256(candidate)
    return candidate


def validate_identity_coverage_candidate(
    candidate: Mapping[str, Any],
) -> tuple[str, ...]:
    """Return fail-closed CI contract violations for the v2 candidate."""

    errors: list[str] = []
    if candidate.get("accepted") is not False:
        errors.append("candidate must remain unaccepted")
    if candidate.get("automatic_acceptance") is not False:
        errors.append("automatic acceptance must remain disabled")
    entries = {str(item.get("code")): item for item in _list(candidate.get("entries"))}
    for code in IDENTITY_REQUIRED_CODES:
        contract = _dict(_dict(entries.get(code)).get("identity_continuity"))
        if contract.get("required") is not True:
            errors.append(f"{code}: stable identity continuity is not required")
        if tuple(contract.get("accepted_modes") or ()) != ACCEPTED_IDENTITY_MODES:
            errors.append(f"{code}: accepted identity modes drifted")
        if contract.get("rehearsal_status") != "passed":
            errors.append(f"{code}: identity migration rehearsal has not passed")
    return tuple(errors)


__all__ = [
    "ACCEPTED_IDENTITY_MODES",
    "IDENTITY_REQUIRED_CODES",
    "build_identity_coverage_candidate",
    "evaluate_identity_handoff",
    "evaluate_identity_uniqueness",
    "rehearse_identity_coverage_contract",
    "validate_identity_coverage_candidate",
]
