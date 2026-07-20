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
        },
    )

    service = SnapshotService(
        collector=FakeCollector(),
        config={},
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
