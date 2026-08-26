from __future__ import annotations

import pytest

from truepanel.guidance.recovery import (
    decorate_guidance,
    recovery_contract,
    transition_recovery,
    verification_for_card,
)


def _card(code: str, *, phase: str = "detected", evidence=None, gate=None):
    return {
        "code": code,
        "severity": "warning",
        "summary": f"{code} detected",
        "immediate_actions": [{"title": "Protect data"}],
        "diagnosis": [{"title": "Inspect evidence"}],
        "remediation": [{"title": "Correct fault"}],
        "verification": [{"title": "Recheck telemetry"}],
        "escalation": "Escalate if evidence remains abnormal.",
        "runtime": {
            "phase": phase,
            "evidence": dict(evidence or {}),
            "action_gate": dict(
                gate
                or {
                    "safe_checks": True,
                    "physical_service_ready": False,
                    "destructive_actions_ready": False,
                    "blocked_by": ["identity_not_verified"],
                }
            ),
        },
    }


def test_contract_preserves_safety_gate_and_stable_identity():
    card = _card(
        "storage.smart_warning",
        evidence={"pool": "tank", "bay": 3, "smart_health": "FAILED"},
    )

    first = recovery_contract(card)
    second = recovery_contract(card)

    assert first["incident_id"] == second["incident_id"]
    assert first["state"] == "detected"
    assert first["action_gate"]["safe_checks"] is True
    assert first["action_gate"]["physical_service_ready"] is False
    assert first["action_gate"]["destructive_actions_ready"] is False
    assert first["action_gate"]["blocked_by"] == ["identity_not_verified"]


def test_smart_verification_requires_critical_evidence_to_clear():
    failed = _card(
        "storage.smart_warning",
        phase="verify",
        evidence={
            "smart_health": "FAILED",
            "pending": 2,
            "offline_uncorrectable": 1,
            "media_errors": 0,
            "critical_warning": "0x00",
        },
    )
    healthy = _card(
        "storage.smart_warning",
        phase="verify",
        evidence={
            "smart_health": "PASSED",
            "pending": 0,
            "offline_uncorrectable": 0,
            "media_errors": 0,
            "critical_warning": "0x00",
        },
    )

    assert recovery_contract(failed)["state"] == "verifying"
    resolved = recovery_contract(healthy)
    assert resolved["state"] == "resolved"
    assert resolved["verification"]["status"] == "passed"


def test_fault_verifiers_cover_fan_pool_network_and_thermal():
    fan = _card("cooling.fan_stall", evidence={"current_rpm": 1480})
    pool = _card(
        "storage.pool_degraded",
        evidence={"pool_state": "ONLINE", "resilver_state": {"resilver_running": False}},
    )
    network = _card(
        "network.link_down",
        evidence={"link_up": True, "address": "192.0.2.10"},
    )
    network_no_address = _card(
        "network.link_down",
        evidence={"link_up": True, "address": None},
    )
    thermal = _card(
        "thermal.high_temperature",
        evidence={"current_temperature_c": 68.0, "recovery_threshold_c": 70.0},
    )

    assert verification_for_card(fan)["status"] == "passed"
    assert verification_for_card(pool)["status"] == "passed"
    assert verification_for_card(network)["status"] == "passed"
    assert verification_for_card(network_no_address)["status"] == "pending"
    assert verification_for_card(thermal)["status"] == "passed"


def test_decorate_guidance_does_not_mutate_source():
    card = _card("cooling.fan_stall", evidence={"current_rpm": 0})
    cards = [card]

    decorated = decorate_guidance(cards)

    assert "recovery" not in card
    assert decorated[0]["recovery"]["code"] == "cooling.fan_stall"


def test_recovery_transition_records_timeline_without_changing_gate():
    contract = recovery_contract(_card("network.link_down"))

    reviewing = transition_recovery(contract, "reviewing", "operator_opened")
    diagnosing = transition_recovery(
        reviewing,
        "diagnosing",
        "passive_checks_started",
        automated=True,
        evidence={"link_up": False},
    )

    assert contract["state"] == "detected"
    assert diagnosing["state"] == "diagnosing"
    assert diagnosing["action_gate"] == contract["action_gate"]
    assert diagnosing["timeline"][-1] == {
        "state": "diagnosing",
        "event": "passive_checks_started",
        "automated": True,
        "evidence": {"link_up": False},
    }


def test_invalid_recovery_transition_is_rejected():
    contract = recovery_contract(_card("storage.disk_faulted"))

    with pytest.raises(ValueError, match="invalid recovery transition"):
        transition_recovery(contract, "resolved", "skip_everything")
