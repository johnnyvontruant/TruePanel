from __future__ import annotations

import json
import stat

import pytest

from truepanel.guidance.recovery import recovery_contract
from truepanel.guidance.sessions import RecoverySessionStore


def _card(
    code="network.link_down",
    *,
    phase="detected",
    evidence=None,
):
    return {
        "code": code,
        "severity": "warning",
        "summary": f"{code} detected",
        "immediate_actions": [],
        "diagnosis": [],
        "remediation": [],
        "verification": [],
        "runtime": {
            "phase": phase,
            "evidence": dict(evidence or {}),
            "action_gate": {
                "safe_checks": True,
                "physical_service_ready": False,
                "destructive_actions_ready": False,
                "blocked_by": ["operator_verification_required"],
            },
        },
    }


def _decorated(card):
    payload = dict(card)
    payload["recovery"] = recovery_contract(card)
    return payload


def _health(subsystem, state):
    return {
        "health": {
            "subsystems": {
                subsystem: {
                    "state": state,
                }
            }
        }
    }


def test_operator_progress_survives_status_refresh(tmp_path):
    path = tmp_path / "pathfinder" / "recovery-sessions.json"
    now = [100.0]
    store = RecoverySessionStore(path, clock=lambda: now[0])

    first = store.observe([_decorated(_card())])[0]
    incident_id = first["recovery"]["incident_id"]
    assert first["recovery"]["state"] == "detected"

    now[0] += 1
    store.transition(incident_id, "reviewing", "operator_opened")

    now[0] += 1
    refreshed = store.observe([_decorated(_card())])[0]
    assert refreshed["recovery"]["state"] == "reviewing"
    assert refreshed["recovery"]["timeline"][-1]["event"] == "operator_opened"


def test_workflow_survives_new_store_instance(tmp_path):
    path = tmp_path / "pathfinder" / "recovery-sessions.json"
    now = [200.0]
    first_store = RecoverySessionStore(path, clock=lambda: now[0])
    observed = first_store.observe([_decorated(_card())])[0]
    incident_id = observed["recovery"]["incident_id"]
    first_store.transition(incident_id, "reviewing", "operator_opened")

    now[0] += 10
    second_store = RecoverySessionStore(path, clock=lambda: now[0])
    restored = second_store.observe([_decorated(_card())])[0]

    assert restored["recovery"]["state"] == "reviewing"
    assert any(
        event["event"] == "operator_opened"
        for event in restored["recovery"]["timeline"]
    )


def test_live_phase_can_advance_but_not_rewind_operator_workflow(tmp_path):
    store = RecoverySessionStore(tmp_path / "sessions.json", clock=lambda: 300.0)
    initial = store.observe([_decorated(_card())])[0]
    incident_id = initial["recovery"]["incident_id"]
    store.transition(incident_id, "reviewing", "operator_opened")
    store.transition(incident_id, "diagnosing", "checks_started")

    advanced = store.observe([_decorated(_card(phase="prepare_repair"))])[0]
    assert advanced["recovery"]["state"] == "repairing"
    assert advanced["recovery"]["timeline"][-1]["event"] == "telemetry_phase_advanced"

    stale_snapshot = store.observe([_decorated(_card(phase="detected"))])[0]
    assert stale_snapshot["recovery"]["state"] == "repairing"


def test_machine_verification_closes_verifying_workflow(tmp_path):
    path = tmp_path / "sessions.json"
    store = RecoverySessionStore(path, clock=lambda: 400.0)

    failing = _card(
        "network.link_down",
        phase="verify",
        evidence={"link_up": False, "address": None, "interface": "eth0"},
    )
    first = store.observe([_decorated(failing)])[0]
    assert first["recovery"]["state"] == "verifying"
    assert first["recovery"]["verification"]["status"] == "pending"

    healthy = _card(
        "network.link_down",
        phase="verify",
        evidence={
            "link_up": True,
            "address": "192.0.2.10",
            "interface": "eth0",
        },
    )
    resolved = store.observe([_decorated(healthy)])[0]

    assert resolved["recovery"]["state"] == "resolved"
    assert resolved["recovery"]["verification"]["status"] == "passed"
    assert resolved["recovery"]["timeline"][-1] == {
        "state": "resolved",
        "event": "verification_passed",
        "automated": True,
        "evidence": {"strategy": "primary_link_recheck"},
    }


def test_disappeared_fault_requires_repeated_nominal_health_before_resolution(tmp_path):
    now = [450.0]
    store = RecoverySessionStore(
        tmp_path / "sessions.json",
        clock=lambda: now[0],
        clear_observations_required=2,
    )
    observed = store.observe([_decorated(_card("network.link_down"))])[0]
    incident_id = observed["recovery"]["incident_id"]
    store.transition(incident_id, "reviewing", "operator_opened")
    store.transition(incident_id, "diagnosing", "checks_started")
    store.transition(incident_id, "verifying", "begin_verification")

    now[0] += 1
    store.observe_snapshot([], _health("network", "NOMINAL"))
    first_clear = store.snapshot()["sessions"][0]
    assert first_clear["incident_id"] == incident_id
    assert first_clear["state"] == "verifying"
    assert first_clear["clear_observations"] == 1

    now[0] += 1
    store.observe_snapshot([], _health("network", "NOMINAL"))
    resolved = store.snapshot()["sessions"][0]
    assert resolved["state"] == "resolved"
    assert resolved["clear_observations"] == 2
    assert resolved["timeline"][-1] == {
        "state": "resolved",
        "event": "subsystem_health_verified",
        "automated": True,
        "evidence": {
            "subsystem": "network",
            "state": "NOMINAL",
            "observations": 2,
        },
    }


def test_missing_or_unknown_health_cannot_close_disappeared_fault(tmp_path):
    store = RecoverySessionStore(tmp_path / "sessions.json")
    observed = store.observe([_decorated(_card("cooling.fan_stall"))])[0]
    incident_id = observed["recovery"]["incident_id"]
    store.transition(incident_id, "reviewing", "operator_opened")
    store.transition(incident_id, "diagnosing", "checks_started")
    store.transition(incident_id, "verifying", "begin_verification")

    store.observe_snapshot([], {})
    store.observe_snapshot([], _health("cooling", "UNKNOWN"))
    store.observe_snapshot([], _health("cooling", "DEGRADED"))

    session = store.snapshot()["sessions"][0]
    assert session["state"] == "verifying"
    assert session["clear_observations"] == 0


def test_disappeared_fault_can_advance_to_verification_only_from_nominal_health(tmp_path):
    store = RecoverySessionStore(
        tmp_path / "sessions.json",
        clear_observations_required=2,
    )
    observed = store.observe([_decorated(_card("storage.pool_degraded"))])[0]
    incident_id = observed["recovery"]["incident_id"]
    store.transition(incident_id, "reviewing", "operator_opened")
    store.transition(incident_id, "diagnosing", "checks_started")
    store.transition(incident_id, "repairing", "repair_in_progress")

    store.observe_snapshot([], _health("storage", "NOMINAL"))
    store.observe_snapshot([], _health("storage", "NOMINAL"))

    session = store.snapshot()["sessions"][0]
    assert session["state"] == "resolved"
    assert any(
        event["event"] == "fault_condition_cleared"
        and event["state"] == "verifying"
        for event in session["timeline"]
    )
    assert session["timeline"][-1]["event"] == "subsystem_health_verified"


def test_same_incident_reopens_when_verified_fault_reappears(tmp_path):
    path = tmp_path / "sessions.json"
    store = RecoverySessionStore(path, clock=lambda: 500.0)

    healthy = _card(
        "network.link_down",
        phase="verify",
        evidence={
            "link_up": True,
            "address": "192.0.2.10",
            "interface": "eth0",
        },
    )
    resolved = store.observe([_decorated(healthy)])[0]
    assert resolved["recovery"]["state"] == "resolved"

    failed_again = _card(
        "network.link_down",
        phase="detected",
        evidence={"link_up": False, "address": None, "interface": "eth0"},
    )
    reopened = store.observe([_decorated(failed_again)])[0]

    assert reopened["recovery"]["state"] == "detected"
    assert reopened["recovery"]["timeline"][-1] == {
        "state": "detected",
        "event": "incident_reappeared",
        "automated": True,
    }


def test_store_persists_metadata_only_without_live_evidence(tmp_path):
    path = tmp_path / "private" / "recovery-sessions.json"
    store = RecoverySessionStore(path, clock=lambda: 600.0)
    card = _card(
        "storage.smart_warning",
        evidence={
            "pool": "tank",
            "device": "sdc",
            "serial_last4": "ABCD",
            "pending": 5,
        },
    )

    store.observe([_decorated(card)])
    raw = path.read_text(encoding="utf-8")
    payload = json.loads(raw)

    assert payload["metadata_only"] is True
    assert "serial_last4" not in raw
    assert '"device"' not in raw
    assert '"pending"' not in raw
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_persistence_failure_does_not_break_live_recovery(monkeypatch, tmp_path):
    store = RecoverySessionStore(tmp_path / "blocked" / "sessions.json")

    def denied(*_args, **_kwargs):
        raise PermissionError("blocked")

    monkeypatch.setattr("pathlib.Path.mkdir", denied)
    observed = store.observe([_decorated(_card())])[0]

    assert observed["recovery"]["state"] == "detected"
    assert observed["recovery"]["action_gate"]["destructive_actions_ready"] is False


def test_invalid_manual_transition_remains_rejected(tmp_path):
    store = RecoverySessionStore(tmp_path / "sessions.json", clock=lambda: 700.0)
    observed = store.observe([_decorated(_card())])[0]
    incident_id = observed["recovery"]["incident_id"]

    with pytest.raises(ValueError, match="invalid recovery transition"):
        store.transition(incident_id, "resolved", "skip_to_green")


def test_unknown_incident_transition_is_rejected(tmp_path):
    store = RecoverySessionStore(tmp_path / "sessions.json")

    with pytest.raises(KeyError, match="unknown recovery incident"):
        store.transition("recovery:missing", "reviewing", "operator_opened")
