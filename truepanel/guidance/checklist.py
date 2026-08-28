"""Project CHECKLIST: evidence-bound recovery procedure state.

CHECKLIST converts an active operator-guidance card into a deterministic,
read-only procedure model for Mission Control. It never performs hardware,
storage, networking, or fan-control actions. In particular, a checklist may
explain that a destructive step exists while keeping that step blocked until a
separate authority layer explicitly permits it.
"""

from __future__ import annotations

from typing import Any

_PHASE_ORDER = (
    "identify",
    "diagnose",
    "prepare_repair",
    "repair",
    "monitor_recovery",
    "verify",
    "complete",
)

_DRIVE_PREFLIGHT = (
    ("member_identity", "Failed member positively identified", "member_identity_not_verified"),
    ("vdev_topology", "VDEV topology verified", "vdev_topology_not_verified"),
    ("remaining_redundancy", "Remaining redundancy verified", "remaining_redundancy_not_verified"),
    ("physical_bay", "Physical bay positively identified", "physical_bay_not_verified"),
    ("device_identity", "Current Linux device verified", "device_not_verified"),
    ("capacity", "Failed-member capacity verified", "capacity_not_verified"),
    (
        "service_procedure",
        "Chassis service procedure verified",
        "chassis_service_procedure_not_verified",
    ),
    (
        "backup_acknowledgement",
        "Current backup acknowledged",
        "backup_acknowledgement_required",
    ),
    (
        "replacement_candidate",
        "Replacement candidate validated",
        "replacement_candidate_not_validated",
    ),
)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _phase_index(phase: str) -> int:
    try:
        return _PHASE_ORDER.index(phase)
    except ValueError:
        return 0


def _procedure_step(
    step: dict[str, Any],
    *,
    section: str,
    action_gate: dict[str, Any],
) -> dict[str, Any]:
    destructive = bool(step.get("destructive", False))
    requires_shutdown = bool(step.get("requires_shutdown", False))
    risk = _text(step.get("risk")) or "safe"

    blocked_by: list[str] = []
    if destructive and not action_gate.get("destructive_actions_ready", False):
        blocked_by.append("destructive_action_authority_required")
    if requires_shutdown:
        blocked_by.append("shutdown_state_not_verified")

    return {
        "section": section,
        "title": _text(step.get("title")),
        "detail": _text(step.get("detail")),
        "risk": risk,
        "destructive": destructive,
        "requires_shutdown": requires_shutdown,
        "state": "blocked" if blocked_by else "pending",
        "blocked_by": blocked_by,
    }


def _drive_preflight(
    runtime: dict[str, Any],
    action_gate: dict[str, Any],
) -> list[dict[str, Any]]:
    blocked = {
        _text(reason)
        for reason in _list(action_gate.get("blocked_by"))
        if _text(reason)
    }
    results: list[dict[str, Any]] = []

    for key, title, blocker in _DRIVE_PREFLIGHT:
        is_blocked = blocker in blocked
        results.append(
            {
                "key": key,
                "title": title,
                "state": "hold" if is_blocked else "verified",
                "blocked_by": [blocker] if is_blocked else [],
            }
        )

    activity = _dict(_dict(runtime.get("evidence")).get("resilver_state"))
    recovery_running = bool(activity.get("resilver_running", False))
    results.append(
        {
            "key": "recovery_activity",
            "title": "Conflicting replacement activity clear",
            "state": "monitor" if recovery_running else "verified",
            "blocked_by": ["resilver_in_progress"] if recovery_running else [],
        }
    )
    return results


def checklist_for_guidance(card: dict[str, Any]) -> dict[str, Any]:
    """Build a read-only checklist from one active guidance card.

    The function deliberately does not infer completion of human actions from
    their position in a procedure. Only facts represented by runtime evidence
    or action gates may be marked ``verified``. Human remediation remains
    ``pending`` or ``blocked`` until a future authority/acknowledgement layer
    records explicit evidence.
    """

    runtime = _dict(card.get("runtime"))
    action_gate = _dict(runtime.get("action_gate"))
    phase = _text(runtime.get("phase")) or "identify"
    code = _text(card.get("code"))

    sections: list[dict[str, Any]] = []
    for field, label in (
        ("immediate_actions", "Immediate actions"),
        ("diagnosis", "Diagnosis"),
        ("remediation", "Remediation"),
        ("verification", "Verification"),
    ):
        steps = [
            _procedure_step(
                step,
                section=field,
                action_gate=action_gate,
            )
            for step in _list(card.get(field))
            if isinstance(step, dict)
        ]
        if steps:
            sections.append({"key": field, "title": label, "steps": steps})

    preflight: list[dict[str, Any]] = []
    if code == "storage.disk_faulted":
        preflight = _drive_preflight(runtime, action_gate)

    holds = [
        item
        for item in preflight
        if item.get("state") in {"hold", "monitor"}
    ]
    blocked_steps = [
        step
        for section in sections
        for step in section["steps"]
        if step.get("state") == "blocked"
    ]

    if phase == "complete":
        status = "complete"
    elif holds:
        status = "hold"
    elif blocked_steps:
        status = "ready_with_gates"
    else:
        status = "ready"

    verified = sum(item.get("state") == "verified" for item in preflight)
    total = len(preflight)

    return {
        "version": 1,
        "code": code,
        "title": _text(card.get("title")),
        "severity": _text(card.get("severity")),
        "active": bool(runtime.get("active", False)),
        "phase": phase,
        "phase_index": _phase_index(phase),
        "status": status,
        "evidence": _dict(runtime.get("evidence")),
        "preflight": preflight,
        "progress": {
            "verified": verified,
            "total": total,
        },
        "sections": sections,
        "action_gate": {
            "safe_checks": bool(action_gate.get("safe_checks", False)),
            "physical_service_ready": bool(
                action_gate.get("physical_service_ready", False)
            ),
            "destructive_actions_ready": bool(
                action_gate.get("destructive_actions_ready", False)
            ),
            "blocked_by": list(_list(action_gate.get("blocked_by"))),
        },
        "read_only": True,
    }


def checklists_for_guidance(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build CHECKLIST procedure state for every active guidance card."""

    return [
        checklist_for_guidance(card)
        for card in cards
        if isinstance(card, dict)
        and _dict(card.get("runtime")).get("active") is True
    ]


__all__ = ["checklist_for_guidance", "checklists_for_guidance"]
