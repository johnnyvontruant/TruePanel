import json

from truepanel.hardware.fan_control import (
    FanControlDecision,
    FanProfile,
)
from truepanel.history.fan_control import (
    FanControlHistory,
    event_from_decision,
)


def decision():
    return FanControlDecision(
        accepted=True,
        requested_profile=(
            FanProfile.AFTERBURNERS
        ),
        effective_profile=(
            FanProfile.AFTERBURNERS
        ),
        pwm=255,
        reason="Afterburners requested.",
    )


def telemetry():
    return {
        "fan_status": {
            "fan_channels": [
                {
                    "number": 1,
                    "rpm": 1500,
                    "pwm": 255,
                    "pwm_mode": "Manual",
                },
                {
                    "number": 2,
                    "rpm": 1450,
                    "pwm": 255,
                    "pwm_mode": "Manual",
                },
            ]
        },
        "temperatures_c": (
            62,
            51,
            48,
        ),
        "telemetry_fresh": True,
    }


def test_event_from_decision():
    event = event_from_decision(
        decision(),
        source="manual",
        telemetry=telemetry(),
        timestamp=100.0,
    )

    assert event["timestamp"] == 100.0
    assert event["source"] == "manual"
    assert (
        event["effective_profile"]
        == "afterburners"
    )
    assert event["decision_pwm"] == 255
    assert event["fan_rpm"] == {
        "1": 1500,
        "2": 1450,
    }
    assert event["temperatures_c"] == [
        62.0,
        51.0,
        48.0,
    ]


def test_history_appends_and_reads(tmp_path):
    path = tmp_path / "fan-control.jsonl"
    history = FanControlHistory(
        path,
        clock=lambda: 100.0,
    )

    assert history.append(
        {
            "source": "manual",
            "reason": "test",
        }
    )

    events = history.read(limit=10)

    assert len(events) == 1
    assert events[0]["event_type"] == (
        "fan_control"
    )
    assert events[0]["timestamp"] == 100.0


def test_history_skips_invalid_lines(
    tmp_path,
):
    path = tmp_path / "fan-control.jsonl"
    path.write_text(
        json.dumps(
            {
                "timestamp": 1,
                "source": "manual",
            }
        )
        + "\nnot-json\n"
        + json.dumps(
            {
                "timestamp": 2,
                "source": "timeout",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    history = FanControlHistory(path)
    events = history.read(limit=10)

    assert len(events) == 2
    assert events[-1]["source"] == "timeout"
