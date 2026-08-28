"""Project CHECKLIST cockpit procedure payloads.

CHECKLIST is a presentation/state adapter, not a second repair engine. Generic
operator guidance supplies the procedure text, while Project Lifeline remains
the authority for evidence-bound drive-repair phases and gates. This module
never performs hardware, storage, network, or fan-control actions.
"""

from __future__ import annotations

from typing import Any


_GATE_CLEARANCE: dict[str, dict[str, str]] = {
    "member_identity": {
        "kind": "machine_evidence",
        "clears_when": (
            "Pool, VDEV, logical member identity, and fault evidence agree."
        ),
    },
    "redundancy": {
        "kind": "machine_evidence",
        "clears_when": (
            "VDEV topology and remaining fault tolerance are observed."
        ),
    },
    "physical_identity": {
        "kind": "machine_evidence",
        "clears_when": (
            "TruePanel independently correlates the logical member to the "
            "physical bay."
        ),
    },
    "service_procedure": {
        "kind": "verified_procedure",
        "clears_when": (
            "A chassis/model-specific service procedure is verified for this "
            "host."
        ),
    },
    "backup_acknowledgement": {
        "kind": "operator_checkpoint",
        "clears_when": (
            "Use the guarded Lifeline Backup State acknowledgement after "
            "reviewing the current backup and redundancy state."
        ),
    },
    "replacement_candidate": {
        "kind": "replacement_media",
        "clears_when": (
            "Attach or detect replacement media and let Lifeline verify exact "
            "identity, minimum capacity, pool membership, ambiguity, and "
            "preserved-data risk."
        ),
    },
    "replacement_confirmation": {
        "kind": "authority_boundary",
        "clears_when": (
            "Only after replacement media validates, a future guarded "
            "write-capable workflow may capture exact-device confirmation. "
            "This checkpoint never grants storage execution authority by "
            "itself."
        ),
    },
}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _humanize(value: Any) -> str:
    return _text(value).replace("_", " ")


def _procedure_step(step: dict[str, Any], *, section: str) -> dict[str, Any]:
    return {
        "section": section,
        "title": _text(step.get("title")),
        "detail": _text(step.get("detail")),
        "risk": _text(step.get("risk")) or "safe",
        "destructive": bool(step.get("destructive", False)),
        "requires_shutdown": bool(step.get("requires_shutdown", False)),
        "state": "pending",
    }


def _sections(card: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for field, label in (
        ("immediate_actions", "Immediate actions"),
        ("diagnosis", "Diagnosis"),
        ("remediation", "Remediation"),
        ("verification", "Verification"),
    ):
        steps = [
            _procedure_step(step, section=field)
            for step in _list(card.get(field))
            if isinstance(step, dict)
        ]
        if steps:
            results.append({"key": field, "title": label, "steps": steps})
    return results


def _gate_condition(code: str, session: dict[str, Any]) -> str:
    if code == "service_procedure":
        return "The chassis-specific service procedure is not yet verified."
    if code == "backup_acknowledgement":
        return "The guarded backup-state acknowledgement has not been recorded."
    if code == "replacement_candidate":
        replacement = _dict(session.get("replacement"))
        if replacement.get("detected") is not True:
            return "No replacement candidate is currently detected."
        reasons = [
            _humanize(item)
            for item in _list(replacement.get("reasons"))
            if _text(item)
        ]
        if reasons:
            return "Replacement validation is blocked by: " + "; ".join(reasons) + "."
        return "Replacement media is present but validation is not complete."
    if code == "replacement_confirmation":
        replacement = _dict(session.get("replacement"))
        if replacement.get("valid") is not True:
            return (
                "Replacement media is not yet validated, so exact-device "
                "confirmation is not applicable."
            )
        return (
            "Replacement media is validated, but storage execution authority "
            "remains intentionally absent."
        )
    return ""


def _lifeline_preflight(session: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for gate in _list(session.get("gates")):
        if not isinstance(gate, dict):
            continue
        code = _text(gate.get("code"))
        satisfied = bool(gate.get("satisfied", False))
        clearance = _GATE_CLEARANCE.get(code, {})
        blocker_kind = _text(clearance.get("kind")) or "machine_evidence"
        clears_when = _text(clearance.get("clears_when"))
        current_condition = "" if satisfied else _gate_condition(code, session)
        detail = _text(gate.get("detail"))

        if not satisfied:
            additions = []
            if current_condition:
                additions.append(current_condition)
            if clears_when:
                additions.append(f"Clear condition: {clears_when}")
            if additions:
                detail = " ".join([detail, *additions]).strip()

        state = "verified" if satisfied else "hold"
        if not satisfied and blocker_kind == "authority_boundary":
            state = "blocked"

        results.append(
            {
                "key": code,
                "title": _text(gate.get("title")),
                "detail": detail,
                "risk": _text(gate.get("risk")) or "safe",
                "state": state,
                "blocker_kind": blocker_kind,
                "clears_when": clears_when,
                "current_condition": current_condition,
                "authority_boundary": blocker_kind == "authority_boundary",
            }
        )
    return results


def _hold_state(preflight: list[dict[str, Any]]) -> dict[str, Any]:
    holds = [item for item in preflight if item.get("state") == "hold"]
    boundaries = [
        item
        for item in preflight
        if item.get("authority_boundary") is True
        and item.get("state") != "verified"
    ]
    unresolved = [*holds, *boundaries]
    next_gate = holds[0] if holds else (boundaries[0] if boundaries else None)

    return {
        "remaining": len(unresolved),
        "current": len(holds),
        "authority_boundaries": len(boundaries),
        "keys": [_text(item.get("key")) for item in unresolved],
        "titles": [_text(item.get("title")) for item in unresolved],
        "next_gate": (
            {
                "key": _text(next_gate.get("key")),
                "title": _text(next_gate.get("title")),
                "blocker_kind": _text(next_gate.get("blocker_kind")),
                "clears_when": _text(next_gate.get("clears_when")),
            }
            if isinstance(next_gate, dict)
            else None
        ),
    }


def _status(session: dict[str, Any], preflight: list[dict[str, Any]]) -> str:
    phase = _text(session.get("phase"))
    if phase == "complete":
        return "complete"
    if phase == "monitor_recovery":
        return "monitor"
    if session.get("write_preconditions_complete") is True:
        return "authority_hold"
    if any(item.get("state") == "hold" for item in preflight):
        return "hold"
    if any(
        item.get("authority_boundary") is True
        and item.get("state") != "verified"
        for item in preflight
    ):
        return "authority_hold"
    return "ready"


def _recovery_kind(session: dict[str, Any]) -> str:
    """Describe the recovery authority represented by a Lifeline session.

    CHECKLIST presentation must not infer drive-replacement controls from one
    particular fault code. SMART pre-failure and ZFS-faulted-member guidance can
    both converge on the same evidence-bound drive-recovery session.
    """

    if not session:
        return "generic"

    target = _dict(session.get("target"))
    has_storage_identity = bool(target.get("pool") or target.get("member_id"))
    has_physical_identity = bool(target.get("device") or target.get("bay"))
    if has_storage_identity and has_physical_identity:
        return "drive_replacement"
    return "lifeline"


def _summary(base: str, hold: dict[str, Any]) -> str:
    remaining = int(hold.get("remaining", 0) or 0)
    if remaining <= 0:
        return base

    current = int(hold.get("current", 0) or 0)
    boundaries = int(hold.get("authority_boundaries", 0) or 0)
    titles = [
        _text(item)
        for item in _list(hold.get("titles"))
        if _text(item)
    ]
    next_gate = _dict(hold.get("next_gate"))

    pieces = [base] if base else []
    pieces.append(
        f"HOLD: {remaining} unresolved recovery gate"
        f"{'s' if remaining != 1 else ''} remain."
    )
    if current and titles:
        current_titles = titles[:current]
        pieces.append("Current blockers: " + "; ".join(current_titles) + ".")
    if boundaries:
        boundary_titles = titles[current:]
        if boundary_titles:
            pieces.append("Authority boundary: " + "; ".join(boundary_titles) + ".")
    if next_gate and _text(next_gate.get("title")):
        prefix = "Next safe checkpoint" if current else "Remaining authority checkpoint"
        pieces.append(f"{prefix}: {_text(next_gate.get('title'))}.")
    return " ".join(piece for piece in pieces if piece)


def checklist_for_guidance(card: dict[str, Any]) -> dict[str, Any]:
    """Build a read-only cockpit checklist from one active guidance card.

    CHECKLIST never marks human procedure text complete merely because the
    workflow advanced. For drive recovery, only Lifeline gates backed by
    observed evidence or explicit acknowledgements may be marked verified.
    """

    runtime = _dict(card.get("runtime"))
    session = _dict(card.get("repair_session"))
    preflight = _lifeline_preflight(session)
    verified = sum(item.get("state") == "verified" for item in preflight)
    hold = _hold_state(preflight)

    phase = _text(session.get("phase")) or _text(runtime.get("phase")) or "diagnose"
    phase_index = session.get("phase_index")
    phase_count = session.get("phase_count")
    base_summary = _text(session.get("summary")) or _text(card.get("summary"))

    return {
        "version": 1,
        "code": _text(card.get("code")),
        "title": _text(session.get("title")) or _text(card.get("title")),
        "summary": _summary(base_summary, hold),
        "severity": _text(card.get("severity")),
        "active": bool(runtime.get("active", False)),
        "phase": phase,
        "phase_index": phase_index,
        "phase_count": phase_count,
        "status": _status(session, preflight),
        "recovery_kind": _recovery_kind(session),
        "target": _dict(session.get("target")),
        "evidence": _dict(runtime.get("evidence")),
        "preflight": preflight,
        "progress": {
            "verified": verified,
            "total": len(preflight),
            "remaining": int(hold.get("remaining", 0) or 0),
        },
        "hold": hold,
        "sections": _sections(card),
        "warnings": _list(session.get("warnings")),
        "blocked_by": _list(session.get("blocked_by")),
        "capabilities": {
            "can_identify_bay": bool(session.get("can_identify_bay", False)),
            "can_begin_physical_service": bool(
                session.get("can_begin_physical_service", False)
            ),
            "can_prepare_replacement": bool(
                session.get("can_prepare_replacement", False)
            ),
            "write_preconditions_complete": bool(
                session.get("write_preconditions_complete", False)
            ),
            "can_execute_replacement": bool(
                session.get("can_execute_replacement", False)
            ),
        },
        "read_only": True,
    }


def checklists_for_guidance(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build CHECKLIST payloads for active operator-guidance cards."""

    return [
        checklist_for_guidance(card)
        for card in cards
        if isinstance(card, dict)
        and _dict(card.get("runtime")).get("active") is True
    ]


__all__ = ["checklist_for_guidance", "checklists_for_guidance"]
