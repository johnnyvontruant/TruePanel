import json

import pytest

from truepanel.history.thermal_commissioning import (
    THERMAL_COMMISSIONING_ACTIONS,
    ThermalCommissioningHistory,
    commissioning_event,
)


def test_action_vocabulary_is_stable():
    assert THERMAL_COMMISSIONING_ACTIONS == (
        "supervised_started",
        "supervised_disarmed",
        "supervised_expired",
        "supervised_safety_cancelled",
        "automatic_lease_started",
        "automatic_lease_cancelled",
        "automatic_lease_expired",
        "automatic_lease_safety_cancelled",
    )


def test_event_is_normalized():
    event = commissioning_event(
        lifecycle_action="supervised_started",
        reason="Session started.",
        commissioning_state="supervised_live",
        active_profile="balanced",
        control_authority="manual",
        lease_remaining=120,
        timestamp=100,
    )

    assert event == {
        "schema_version": 1,
        "event_type": "thermal_commissioning",
        "timestamp": 100.0,
        "lifecycle_action": "supervised_started",
        "reason": "Session started.",
        "commissioning_state": "supervised_live",
        "active_profile": "balanced",
        "control_authority": "manual",
        "lease_remaining": 120.0,
    }


def test_unknown_action_is_rejected():
    with pytest.raises(ValueError):
        commissioning_event(
            lifecycle_action="unknown",
            reason="Invalid.",
            commissioning_state="configured",
            active_profile="automatic",
            control_authority="automatic",
        )


def test_history_appends_and_reads(tmp_path):
    history = ThermalCommissioningHistory(
        tmp_path / "commissioning.jsonl",
        clock=lambda: 100.0,
    )

    assert history.append(
        {
            "lifecycle_action": "supervised_expired",
            "reason": "Lease expired.",
        }
    )

    events = history.read(limit=10)

    assert len(events) == 1
    assert (
        events[0]["event_type"]
        == "thermal_commissioning"
    )
    assert events[0]["timestamp"] == 100.0


def test_history_skips_invalid_lines(tmp_path):
    path = tmp_path / "commissioning.jsonl"

    path.write_text(
        json.dumps(
            {
                "timestamp": 1,
                "lifecycle_action": "supervised_started",
            }
        )
        + "\nnot-json\n"
        + json.dumps(
            {
                "timestamp": 2,
                "lifecycle_action": "supervised_expired",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    events = ThermalCommissioningHistory(
        path
    ).read(limit=10)

    assert len(events) == 2
    assert (
        events[-1]["lifecycle_action"]
        == "supervised_expired"
    )


def test_history_prunes_old_events(tmp_path):
    history = ThermalCommissioningHistory(
        tmp_path / "commissioning.jsonl",
        maximum_events=3,
    )

    for index in range(5):
        history.append(
            {
                "timestamp": index,
                "lifecycle_action": (
                    "supervised_started"
                ),
            }
        )

    assert [
        event["timestamp"]
        for event in history.read(limit=10)
    ] == [
        2.0,
        3.0,
        4.0,
    ]


def test_disabled_history_does_not_write(tmp_path):
    path = tmp_path / "commissioning.jsonl"

    history = ThermalCommissioningHistory(
        path,
        enabled=False,
    )

    assert history.append(
        {
            "lifecycle_action": "supervised_started",
        }
    ) is False

    assert not path.exists()
