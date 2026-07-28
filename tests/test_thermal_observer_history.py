import json

from truepanel.hardware.fan_control import (
    FanProfile,
)
from truepanel.hardware.thermal_fan_policy import (
    ThermalFanRecommendation,
)
from truepanel.history.thermal_observer import (
    ThermalObserverHistory,
    event_from_recommendation,
)


def recommendation(
    *,
    profile=FanProfile.BALANCED,
    temperature=47.0,
    valid=True,
    changed=True,
):
    return ThermalFanRecommendation(
        recommended_profile=profile,
        hottest_temperature_c=temperature,
        telemetry_valid=valid,
        changed=changed,
        reason=(
            "Thermal recommendation changed."
        ),
    )


def test_event_from_recommendation():
    event = event_from_recommendation(
        recommendation(),
        active_profile="automatic",
        control_authority="automatic",
        timestamp=100.0,
    )

    assert event == {
        "schema_version": 1,
        "event_type": "thermal_observer",
        "timestamp": 100.0,
        "policy_mode": "observe_only",
        "recommended_profile": "balanced",
        "active_profile": "automatic",
        "control_authority": "automatic",
        "hottest_temperature_c": 47.0,
        "telemetry_valid": True,
        "recommendation_changed": True,
        "reason": (
            "Thermal recommendation changed."
        ),
    }


def test_history_appends_and_reads(
    tmp_path,
):
    history = ThermalObserverHistory(
        tmp_path / "thermal.jsonl",
        clock=lambda: 100.0,
    )

    assert history.append(
        event_from_recommendation(
            recommendation(),
            timestamp=100.0,
        )
    )

    events = history.read(
        limit=10
    )

    assert len(events) == 1
    assert (
        events[0]["recommended_profile"]
        == "balanced"
    )
    assert events[0]["timestamp"] == 100.0


def test_history_skips_invalid_lines(
    tmp_path,
):
    path = tmp_path / "thermal.jsonl"

    path.write_text(
        json.dumps(
            {
                "timestamp": 1,
                "recommended_profile": "quiet",
            }
        )
        + "\nnot-json\n"
        + json.dumps(
            {
                "timestamp": 2,
                "recommended_profile": "balanced",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    history = ThermalObserverHistory(
        path
    )
    events = history.read(
        limit=10
    )

    assert len(events) == 2
    assert (
        events[-1]["recommended_profile"]
        == "balanced"
    )


def test_history_prunes_old_events(
    tmp_path,
):
    history = ThermalObserverHistory(
        tmp_path / "thermal.jsonl",
        maximum_events=3,
    )

    for index in range(5):
        history.append(
            {
                "timestamp": index,
                "recommended_profile": "balanced",
            }
        )

    events = history.read(
        limit=10
    )

    assert len(events) == 3
    assert [
        event["timestamp"]
        for event in events
    ] == [
        2.0,
        3.0,
        4.0,
    ]


def test_disabled_history_does_not_write(
    tmp_path,
):
    path = tmp_path / "thermal.jsonl"
    history = ThermalObserverHistory(
        path,
        enabled=False,
    )

    assert history.append(
        {
            "recommended_profile": "quiet",
        }
    ) is False

    assert not path.exists()


def test_module_is_observe_only():
    from pathlib import Path

    source = Path(
        "truepanel/history/"
        "thermal_observer.py"
    ).read_text(
        encoding="utf-8",
    )

    for forbidden in (
        "request_profile",
        "service.tick",
        "FanHardwareExecutor",
        "set_manual_pwm",
        "write_int",
        "/sys/",
    ):
        assert forbidden not in source
