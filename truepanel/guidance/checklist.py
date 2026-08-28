"""Project CHECKLIST cockpit procedure payloads.

CHECKLIST is a presentation/state adapter, not a second repair engine. Generic
operator guidance supplies the procedure text, while Project Lifeline remains
the authority for evidence-bound drive-repair phases and gates. This module
never performs hardware, storage, network, or fan-control actions.
"""

from __future__ import annotations

from typing import Any


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


def _lifeline_preflight(session: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for gate in _list(session.get("gates")):
        if not isinstance(gate, dict):
            continue
        satisfied = bool(gate.get("satisfied", False))
        results.append(
            {
                "key": _text(gate.get("code")),
                "title": _text(gate.get("title")),
                "detail": _text(gate.get("detail")),
                "risk": _text(gate.get("risk")) or "safe",
                "state": "verified" if satisfied else "hold",
            }
        )
    return results


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

    phase = _text(session.get("phase")) or _text(runtime.get("phase")) or "diagnose"
    phase_index = session.get("phase_index")
    phase_count = session.get("phase_count")

    return {
        "version": 1,
        "code": _text(card.get("code")),
        "title": _text(session.get("title")) or _text(card.get("title")),
        "summary": _text(session.get("summary")) or _text(card.get("summary")),
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
        },
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
