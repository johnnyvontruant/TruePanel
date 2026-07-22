import json

from truepanel.web.snapshot import (
    SnapshotService,
)


class FakeCollector:
    def update(self):
        return {
            "cpu_percent": 25,
            "ram_percent": 50,
            "uptime_seconds": 1234,
            "load_average": [
                1.0,
                0.5,
                0.25,
            ],
            "pools": [
                {
                    "name": "HDDs",
                    "health": "ONLINE",
                    "percent_used": 78,
                }
            ],
            "temps": [
                {
                    "device": "sda",
                    "temperature": 38,
                }
            ],
            "interfaces": {
                "eth0": (
                    "192.168.0.10"
                ),
            },
        }


def test_status_snapshot_is_read_only(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        (
            "truepanel.web.snapshot."
            "get_fan_status"
        ),
        lambda: {
            "fan1_rpm": 1500,
            "fan2_rpm": 1450,
            "pwm1": 187,
            "pwm2": 187,
            "pwm1_mode": "Auto",
            "pwm2_mode": "Auto",
            "fan_channels": [
                {
                    "number": 1,
                    "rpm": 1500,
                    "alarm": False,
                    "pwm": 187,
                    "pwm_mode": "Auto",
                },
                {
                    "number": 2,
                    "rpm": 1450,
                    "alarm": False,
                    "pwm": 187,
                    "pwm_mode": "Auto",
                },
                {
                    "number": 3,
                    "rpm": 0,
                    "alarm": True,
                    "pwm": 178,
                    "pwm_mode": "Auto",
                },
            ],
        },
    )

    service = SnapshotService(
        collector=FakeCollector(),
        config={
            "hardware": {
                "fans": {
                    "channels": {
                        1: {
                            "label": "Rear Fan 1",
                            "monitored": True,
                        },
                        2: {
                            "label": "Rear Fan 2",
                            "monitored": True,
                        },
                        3: {
                            "label": "Unused Header",
                            "monitored": False,
                        },
                    }
                }
            }
        },
        history_path=(
            tmp_path
            / "history.jsonl"
        ),
        clock=lambda: 100.0,
    )

    payload = service.status()

    assert (
        payload["read_only"]
        is True
    )

    assert (
        payload["timestamp"]
        == 100.0
    )

    assert (
        payload["system"][
            "cpu_percent"
        ]
        == 25.0
    )

    assert (
        payload["fans"][
            "fan1_rpm"
        ]
        == 1500
    )

    assert (
        payload["fans"][
            "channels"
        ][2]
        == {
            "number": 3,
            "label": "Unused Header",
            "monitored": False,
            "rpm": 0,
            "alarm": True,
            "pwm": 178,
            "pwm_mode": "Auto",
        }
    )

    assert (
        payload["storage"][
            "pools"
        ][0]["name"]
        == "HDDs"
    )

    assert (
        payload["network"][0][
            "name"
        ]
        == "eth0"
    )


def test_history_skips_invalid_lines(
    tmp_path,
):
    history_path = (
        tmp_path
        / "telemetry.jsonl"
    )

    history_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": 1,
                        "cpu_percent": 10,
                    }
                ),
                "not-json",
                json.dumps(
                    {
                        "timestamp": 2,
                        "cpu_percent": 20,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    service = SnapshotService(
        collector=FakeCollector(),
        config={},
        history_path=history_path,
    )

    payload = service.history(
        limit=10
    )

    assert (
        payload["read_only"]
        is True
    )

    assert payload["count"] == 2

    assert (
        payload["samples"][1][
            "cpu_percent"
        ]
        == 20
    )


def test_capabilities_disable_writes(
    tmp_path,
):
    service = SnapshotService(
        collector=FakeCollector(),
        config={
            "night_mode": {
                "enabled": True,
            },
            "buzzer": {
                "enabled": True,
            },
            "hardware": {
                "bay_leds": {
                    "enabled": True,
                }
            },
        },
        history_path=(
            tmp_path
            / "history.jsonl"
        ),
    )

    payload = (
        service.capabilities()
    )

    assert (
        payload["safety"][
            "read_only"
        ]
        is True
    )

    assert (
        payload["safety"][
            "remote_writes_enabled"
        ]
        is False
    )

    assert (
        payload[
            "hardware_controls"
        ]["fan_control"]
        is False
    )


def test_fan_control_status_is_disabled_by_default(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        (
            "truepanel.web.snapshot."
            "get_fan_status"
        ),
        lambda: {
            "available": True,
            "fan_channels": [],
        },
    )

    service = SnapshotService(
        collector=FakeCollector(),
        config={
            "hardware": {
                "fan_control": {
                    "enabled": False,
                    "command_timeout": 300,
                    "controlled_channels": [
                        1,
                        2,
                    ],
                }
            }
        },
        history_path=(
            tmp_path
            / "history.jsonl"
        ),
    )

    control = service.status()[
        "fans"
    ]["control"]

    assert control == {
        "configured": True,
        "enabled": False,
        "available": True,
        "connected": False,
        "active_profile": (
            "automatic"
        ),
        "requested_profile": (
            "automatic"
        ),
        "command_timeout": 300,
        "controlled_channels": [
            1,
            2,
        ],
        "remaining_seconds": None,
        "last_reason": (
            "Fan control is disabled."
        ),
    }


def test_fan_control_status_reports_missing_controller(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        (
            "truepanel.web.snapshot."
            "get_fan_status"
        ),
        lambda: {
            "available": False,
            "fan_channels": [],
        },
    )

    service = SnapshotService(
        collector=FakeCollector(),
        config={
            "hardware": {
                "fan_control": {
                    "enabled": True,
                }
            }
        },
        history_path=(
            tmp_path
            / "history.jsonl"
        ),
    )

    control = service.status()[
        "fans"
    ]["control"]

    assert control["enabled"] is True
    assert control["available"] is False
    assert control["connected"] is False
    assert control["last_reason"] == (
        "Fintek fan controller is unavailable."
    )


def test_fan_control_capability_follows_feature_flag(
    tmp_path,
):
    disabled = SnapshotService(
        collector=FakeCollector(),
        config={
            "hardware": {
                "fan_control": {
                    "enabled": False,
                }
            }
        },
        history_path=(
            tmp_path
            / "disabled.jsonl"
        ),
    )

    enabled = SnapshotService(
        collector=FakeCollector(),
        config={
            "hardware": {
                "fan_control": {
                    "enabled": True,
                }
            }
        },
        history_path=(
            tmp_path
            / "enabled.jsonl"
        ),
    )

    assert (
        disabled.capabilities()[
            "hardware_controls"
        ]["fan_control"]
        is False
    )

    assert (
        enabled.capabilities()[
            "hardware_controls"
        ]["fan_control"]
        is True
    )


def test_snapshot_does_not_import_fan_control_modules():
    import json
    import subprocess
    import sys

    script = """
import json
import sys

from truepanel.web.snapshot import SnapshotService

SnapshotService()

modules = sorted(
    name
    for name in sys.modules
    if name in {
        "truepanel.hardware.fan_control",
        "truepanel.hardware.fan_executor",
        "truepanel.hardware.fan_service",
    }
)

print(json.dumps(modules))
"""

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(
        result.stdout
    ) == []
