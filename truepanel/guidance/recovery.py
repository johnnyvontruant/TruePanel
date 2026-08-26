"""Stateful, read-only recovery contracts for Mission Control guidance.

Pathfinder turns a guidance card into a small recovery state machine. The
contract is intentionally advisory: it can evaluate telemetry and recommend a
next phase, but it cannot perform physical service, storage mutation, or grant
hardware-control authority.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any

RECOVERY_SCHEMA_VERSION = 1

_PHASE_TO_STATE = {
    "detected": "detected",
    "identify": "diagnosing",
    "diagnose": "diagnosing",
    "prepare_repair": "repairing",
    "repair": "repairing",
    "monitor_recovery": "verifying",
    "verify": "verifying",
    "resolved": "resolved",
}

_TRANSITIONS = {
    "detected": ("reviewing", "diagnosing"),
    "reviewing": ("diagnosing",),
    "diagnosing": ("repairing", "verifying"),
    "repairing": ("verifying",),
    "verifying": ("resolved", "diagnosing", "repairing"),
    "resolved": (),
}


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


def _steps(card: dict[str, Any], key: str) -> list[dict[str, Any]]:
    return [
        deepcopy(step)
        for step in _list(card.get(key))
        if isinstance(step, dict)
    ]


def _identity(card: dict[str, Any]) -> str:
    runtime = _dict(card.get("runtime"))
    evidence = _dict(runtime.get("evidence"))
    identity_fields = (
        "pool",
        "vdev",
        "member_id",
        "bay",
        "device",
        "fan_channel",
        "interface",
        "sensor_label",
        "check_name",
    )
    identity = "|".join(
        _text(evidence.get(field))
        for field in identity_fields
        if _text(evidence.get(field))
    )
    digest = sha256(
        f"{_text(card.get('code'))}|{identity}".encode("utf-8")
    ).hexdigest()[:16]
    return f"recovery:{digest}"


def _state_for_card(card: dict[str, Any]) -> str:
    phase = _text(_dict(card.get("runtime")).get("phase")).lower()
    return _PHASE_TO_STATE.get(phase, "reviewing")


def _smart_verification(card: dict[str, Any]) -> dict[str, Any]:
    evidence = _dict(_dict(card.get("runtime")).get("evidence"))
    healthy = (
        _text(evidence.get("smart_health")).upper() not in {"FAILED"}
        and _integer(evidence.get("pending")) == 0
        and _integer(evidence.get("offline_uncorrectable")) == 0
        and _integer(evidence.get("media_errors")) == 0
        and _text(evidence.get("critical_warning")).lower()
        in {"", "0", "0x00", "0x0"}
    )
    return {
        "strategy": "smart_and_zfs_recheck",
        "automated": True,
        "status": "passed" if healthy else "pending",
        "criteria": (
            "SMART critical evidence clears and ZFS state is independently "
            "rechecked before the incident is resolved."
        ),
    }


def _fan_verification(card: dict[str, Any]) -> dict[str, Any]:
    evidence = _dict(_dict(card.get("runtime")).get("evidence"))
    rpm = _integer(evidence.get("current_rpm"))
    return {
        "strategy": "fan_rpm_recheck",
        "automated": True,
        "status": "passed" if rpm > 0 else "pending",
        "criteria": (
            "The monitored fan reports stable non-zero RPM for repeated "
            "observations and temperatures are not rising."
        ),
    }


def _pool_verification(card: dict[str, Any]) -> dict[str, Any]:
    evidence = _dict(_dict(card.get("runtime")).get("evidence"))
    state = _text(evidence.get("pool_state")).upper()
    activity = _dict(evidence.get("resilver_state"))
    passed = state == "ONLINE" and not activity.get("resilver_running")
    return {
        "strategy": "zfs_pool_recheck",
        "automated": True,
        "status": "passed" if passed else "pending",
        "criteria": (
            "The affected pool returns ONLINE and any resilver completes "
            "without a reported recovery problem."
        ),
    }


def _network_verification(card: dict[str, Any]) -> dict[str, Any]:
    evidence = _dict(_dict(card.get("runtime")).get("evidence"))
    address = _text(evidence.get("address"))
    passed = evidence.get("link_up") is True and bool(address)
    return {
        "strategy": "primary_link_recheck",
        "automated": True,
        "status": "passed" if passed else "pending",
        "criteria": (
            "The primary interface reports link up again and has a usable "
            "address before the incident is resolved."
        ),
    }


def _thermal_verification(card: dict[str, Any]) -> dict[str, Any]:
    evidence = _dict(_dict(card.get("runtime")).get("evidence"))
    temperature = evidence.get("current_temperature_c")
    threshold = evidence.get("recovery_threshold_c")
    passed = False
    if isinstance(temperature, (int, float)) and isinstance(
        threshold, (int, float)
    ):
        passed = temperature < threshold
    return {
        "strategy": "thermal_recheck",
        "automated": True,
        "status": "passed" if passed else "pending",
        "criteria": (
            "Temperature falls below the configured recovery threshold and "
            "remains stable across repeated samples."
        ),
    }


def verification_for_card(card: dict[str, Any]) -> dict[str, Any]:
    """Return the safe telemetry verifier attached to a guidance code."""

    code = _text(card.get("code"))
    if code == "storage.smart_warning":
        return _smart_verification(card)
    if code == "cooling.fan_stall":
        return _fan_verification(card)
    if code in {"storage.pool_degraded", "storage.disk_faulted"}:
        return _pool_verification(card)
    if code == "network.link_down":
        return _network_verification(card)
    if code == "thermal.high_temperature":
        return _thermal_verification(card)
    return {
        "strategy": "operator_and_telemetry_recheck",
        "automated": False,
        "status": "pending",
        "criteria": (
            "Repeat the relevant passive checks and confirm the triggering "
            "evidence is no longer present."
        ),
    }


def recovery_contract(card: dict[str, Any]) -> dict[str, Any]:
    """Project one guidance card into the universal Pathfinder contract."""

    state = _state_for_card(card)
    runtime = _dict(card.get("runtime"))
    gate = _dict(runtime.get("action_gate"))
    verification = verification_for_card(card)

    if state == "verifying" and verification["status"] == "passed":
        state = "resolved"

    return {
        "schema_version": RECOVERY_SCHEMA_VERSION,
        "incident_id": _identity(card),
        "code": _text(card.get("code")),
        "state": state,
        "allowed_transitions": list(_TRANSITIONS[state]),
        "severity": _text(card.get("severity")) or "warning",
        "explanation": _text(card.get("summary")),
        "evidence": deepcopy(_dict(runtime.get("evidence"))),
        "immediate_precautions": _steps(card, "immediate_actions"),
        "diagnostic_steps": _steps(card, "diagnosis"),
        "corrective_steps": _steps(card, "remediation"),
        "verification_steps": _steps(card, "verification"),
        "verification": verification,
        "escalation": _text(card.get("escalation")),
        "action_gate": {
            "safe_checks": gate.get("safe_checks") is True,
            "physical_service_ready": gate.get("physical_service_ready") is True,
            "destructive_actions_ready": gate.get("destructive_actions_ready") is True,
            "blocked_by": list(_list(gate.get("blocked_by"))),
        },
        "timeline": [
            {
                "state": state,
                "event": "guidance_evaluated",
                "automated": True,
            }
        ],
    }


def transition_recovery(
    contract: dict[str, Any],
    next_state: str,
    event: str,
    *,
    automated: bool = False,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Advance a recovery contract and append an immutable timeline event.

    This function only records workflow state. It never performs the repair or
    changes a safety gate. Callers must still satisfy hardware and storage
    interlocks independently.
    """

    current = _text(contract.get("state")).lower()
    target = _text(next_state).lower()
    allowed = _TRANSITIONS.get(current)
    if allowed is None:
        raise ValueError(f"unknown recovery state: {current or '<empty>'}")
    if target not in allowed:
        raise ValueError(f"invalid recovery transition: {current} -> {target}")

    updated = deepcopy(contract)
    updated["state"] = target
    updated["allowed_transitions"] = list(_TRANSITIONS[target])

    timeline = [
        deepcopy(item)
        for item in _list(updated.get("timeline"))
        if isinstance(item, dict)
    ]
    timeline_event: dict[str, Any] = {
        "state": target,
        "event": _text(event) or "state_changed",
        "automated": bool(automated),
    }
    if evidence:
        timeline_event["evidence"] = deepcopy(evidence)
    timeline.append(timeline_event)
    updated["timeline"] = timeline[-64:]
    return updated


def decorate_guidance(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach recovery contracts without changing existing card semantics."""

    decorated = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        payload = deepcopy(card)
        payload["recovery"] = recovery_contract(payload)
        decorated.append(payload)
    return decorated


__all__ = [
    "RECOVERY_SCHEMA_VERSION",
    "decorate_guidance",
    "recovery_contract",
    "transition_recovery",
    "verification_for_card",
]
