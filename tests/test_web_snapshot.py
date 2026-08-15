import json
from pathlib import Path

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
        fan_control_status_path=(
            tmp_path
            / "disabled-fan-control-status.json"
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
        "control_authority": "automatic",
        "safety_hold": False,
        "recovery_pending": False,
        "recovery_healthy_cycles": 0,
        "recovery_required_cycles": 3,
        "thermal_policy_mode": "observe_only",
        "thermal_operator_armed": False,
        "thermal_dry_run": True,
        "thermal_control_state": "blocked",
        "thermal_control_reason": (
            "Thermal control is unavailable."
        ),
        "thermal_simulated_profile": "automatic",
        "thermal_control_cooldown_remaining": 0.0,
        "thermal_supervised_session_active": False,
        "thermal_supervised_session_remaining": 0.0,
        "thermal_commissioning_state": "configured",
        "thermal_recommended_profile": "automatic",
        "thermal_profile_alignment": "telemetry_unavailable",
        "thermal_control_readiness": {
            "ready": False,
            "armed": False,
            "state": "blocked",
            "checks": {
                "policy_allows_automatic": False,
                "controller_connected": False,
                "telemetry_valid": False,
                "safety_clear": True,
                "recovery_clear": True,
                "recommendation_available": False,
                "operator_armed": False,
            },
            "blocking_reasons": [
                (
                    "Thermal policy is not configured "
                    "for automatic control."
                ),
                (
                    "Fan-control runtime is not "
                    "connected."
                ),
                (
                    "Thermal telemetry is unavailable."
                ),
                (
                    "Thermal recommendation is "
                    "unavailable."
                ),
                (
                    "Automatic thermal control has not "
                    "been armed by the operator."
                ),
            ],
        },
        "thermal_hottest_temperature_c": None,
        "thermal_recommendation_reason": (
            "Thermal observer status is unavailable."
        ),
        "thermal_recommendation_changed": False,
        "thermal_telemetry_valid": False,
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
        fan_control_status_path=(
            tmp_path
            / "missing-controller-status.json"
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


def test_snapshot_reads_fresh_fan_control_bridge(
    monkeypatch,
    tmp_path,
):
    from truepanel.hardware.fan_status_bridge import (
        FanControlStatusBridge,
    )

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

    status_path = (
        tmp_path
        / "fan-control-status.json"
    )

    bridge = FanControlStatusBridge(
        status_path,
        clock=lambda: 100.0,
    )

    bridge.publish(
        {
            "enabled": False,
            "connected": False,
            "active_profile": (
                "automatic"
            ),
            "requested_profile": (
                "automatic"
            ),
            "last_reason": (
                "Published by LCD runtime."
            ),
        }
    )

    service = SnapshotService(
        collector=FakeCollector(),
        config={
            "hardware": {
                "fan_control": {
                    "enabled": False,
                }
            }
        },
        fan_control_status_path=(
            status_path
        ),
        history_path=(
            tmp_path
            / "history.jsonl"
        ),
        clock=lambda: 100.0,
    )

    control = service.status()[
        "fans"
    ]["control"]

    assert control["connected"] is False
    assert (
        control["last_reason"]
        == "Published by LCD runtime."
    )
    assert (
        control["status_age_seconds"]
        == 0.0
    )


def test_snapshot_ignores_stale_fan_control_bridge(
    monkeypatch,
    tmp_path,
):
    from truepanel.hardware.fan_status_bridge import (
        FanControlStatusBridge,
    )

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

    status_path = (
        tmp_path
        / "fan-control-status.json"
    )

    bridge = FanControlStatusBridge(
        status_path,
        clock=lambda: 100.0,
    )

    bridge.publish(
        {
            "connected": True,
            "last_reason": "Old status",
        }
    )

    service = SnapshotService(
        collector=FakeCollector(),
        config={
            "hardware": {
                "fan_control": {
                    "enabled": False,
                }
            }
        },
        fan_control_status_path=(
            status_path
        ),
        history_path=(
            tmp_path
            / "history.jsonl"
        ),
        clock=lambda: 131.0,
    )

    control = service.status()[
        "fans"
    ]["control"]

    assert control["connected"] is False
    assert (
        control["last_reason"]
        == "Fan control is disabled."
    )


def test_fan_control_history_payload(
    tmp_path,
):
    history_path = (
        tmp_path
        / "fan-control.jsonl"
    )

    history_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": 1,
                        "source": "manual",
                    }
                ),
                json.dumps(
                    {
                        "timestamp": 2,
                        "source": "timeout",
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
        history_path=(
            tmp_path
            / "telemetry.jsonl"
        ),
        fan_control_history_path=(
            history_path
        ),
    )

    payload = (
        service
        .fan_control_history_payload(
            limit=1
        )
    )

    assert payload["read_only"] is True
    assert payload["count"] == 1
    assert (
        payload["events"][0]["source"]
        == "timeout"
    )


def test_fan_control_history_limit_is_bounded(
    tmp_path,
):
    service = SnapshotService(
        collector=FakeCollector(),
        config={},
        history_path=(
            tmp_path
            / "telemetry.jsonl"
        ),
        fan_control_history_path=(
            tmp_path
            / "fan-control.jsonl"
        ),
    )

    payload = (
        service
        .fan_control_history_payload(
            limit=10000
        )
    )

    assert payload["count"] == 0
    assert payload["read_only"] is True



def test_snapshot_preserves_supervised_thermal_lease():
    source = Path(
        "truepanel/web/snapshot.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        '"thermal_supervised_session_active": bool('
        in source
    )
    assert (
        '"thermal_supervised_session_remaining": ('
        in source
    )
    assert (
        'runtime_status.get(\n'
        '                        "thermal_supervised_session_active"'
        in source
    )
    assert (
        'runtime_status.get(\n'
        '                        "thermal_supervised_session_remaining"'
        in source
    )


def test_snapshot_has_safe_supervised_lease_defaults():
    source = Path(
        "truepanel/web/snapshot.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        '"thermal_supervised_session_active": False'
        in source
    )
    assert (
        '"thermal_supervised_session_remaining": 0.0'
        in source
    )



def test_snapshot_publishes_commissioning_state():
    source = Path(
        "truepanel/web/snapshot.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "thermal_commissioning_state("
        in source
    )
    assert (
        '"thermal_commissioning_state":'
        in source
    )
    assert (
        '"thermal_supervised_session_active"'
        in source
    )
    assert (
        "supervised_session_active=("
        in source
    )



def test_thermal_commissioning_history_payload(
    tmp_path,
):
    history_path = (
        tmp_path
        / "thermal-commissioning.jsonl"
    )

    history_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": 1,
                        "lifecycle_action": (
                            "supervised_started"
                        ),
                    }
                ),
                json.dumps(
                    {
                        "timestamp": 2,
                        "lifecycle_action": (
                            "supervised_expired"
                        ),
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
        history_path=(
            tmp_path
            / "telemetry.jsonl"
        ),
        thermal_commissioning_history_path=(
            history_path
        ),
    )

    payload = (
        service
        .thermal_commissioning_history_payload(
            limit=1
        )
    )

    assert payload["read_only"] is True
    assert payload["count"] == 1
    assert (
        payload["events"][0][
            "lifecycle_action"
        ]
        == "supervised_expired"
    )


def test_commissioning_history_limit_is_bounded(
    tmp_path,
):
    service = SnapshotService(
        collector=FakeCollector(),
        config={},
        history_path=(
            tmp_path
            / "telemetry.jsonl"
        ),
        thermal_commissioning_history_path=(
            tmp_path
            / "thermal-commissioning.jsonl"
        ),
    )

    payload = (
        service
        .thermal_commissioning_history_payload(
            limit=10000
        )
    )

    assert payload["count"] == 0
    assert payload["read_only"] is True



def test_status_snapshot_publishes_lcd_reader_health(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        (
            "truepanel.web.snapshot."
            "get_fan_status"
        ),
        lambda: {},
    )

    lcd_status_path = (
        tmp_path
        / "lcd-reader-status.json"
    )

    from truepanel.hardware.lcd_reader_status_bridge import (
        LCDReaderStatusBridge,
    )

    bridge = LCDReaderStatusBridge(
        lcd_status_path,
        clock=lambda: 100.0,
    )

    bridge.publish(
        {
            "thread_alive": True,
            "dispatcher_alive": True,
            "dispatcher_events": 4,
            "dispatch_queue_depth": 0,
            "replies": 21,
            "button_reports": 4,
            "last_button_mask": 0,
            "last_pressed_button_mask": 2,
            "callback_count": 4,
            "callback_errors": 0,
        }
    )

    service = SnapshotService(
        collector=FakeCollector(),
        config={},
        history_path=(
            tmp_path
            / "history.jsonl"
        ),
        lcd_reader_status_path=(
            lcd_status_path
        ),
        clock=lambda: 100.0,
    )

    lcd_payload = service.status()["lcd"]

    assert lcd_payload["available"] is True
    assert lcd_payload["stale"] is False
    assert (
        lcd_payload["reader"][
            "thread_alive"
        ]
        is True
    )
    assert (
        lcd_payload["reader"][
            "dispatcher_alive"
        ]
        is True
    )
    assert (
        lcd_payload["reader"][
            "dispatcher_events"
        ]
        == 4
    )
    assert (
        lcd_payload["reader"][
            "dispatch_queue_depth"
        ]
        == 0
    )
    assert (
        lcd_payload["reader"][
            "replies"
        ]
        == 21
    )
    assert (
        lcd_payload["reader"][
            "button_reports"
        ]
        == 4
    )
    assert (
        lcd_payload["reader"][
            "last_button_mask"
        ]
        == 0
    )
    assert (
        lcd_payload["reader"][
            "last_pressed_button_mask"
        ]
        == 2
    )


def test_status_snapshot_uses_safe_lcd_defaults(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        (
            "truepanel.web.snapshot."
            "get_fan_status"
        ),
        lambda: {},
    )

    service = SnapshotService(
        collector=FakeCollector(),
        config={},
        history_path=(
            tmp_path
            / "history.jsonl"
        ),
        lcd_reader_status_path=(
            tmp_path
            / "missing-lcd-status.json"
        ),
        lcd_display_status_path=(
            tmp_path
            / "missing-lcd-display-status.json"
        ),
        clock=lambda: 100.0,
    )

    lcd_payload = service.status()["lcd"]

    assert lcd_payload["available"] is False
    assert lcd_payload["stale"] is True
    assert (
        lcd_payload["reader"][
            "thread_alive"
        ]
        is False
    )
    assert (
        lcd_payload["reader"][
            "button_reports"
        ]
        == 0
    )


def test_status_snapshot_publishes_live_lcd_display(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        (
            "truepanel.web.snapshot."
            "get_fan_status"
        ),
        lambda: {},
    )

    reader_path = (
        tmp_path
        / "lcd-reader-status.json"
    )
    display_path = (
        tmp_path
        / "lcd-display-status.json"
    )

    from truepanel.hardware.lcd_display_status_bridge import (
        LCDDisplayStatusBridge,
    )
    from truepanel.hardware.lcd_reader_status_bridge import (
        LCDReaderStatusBridge,
    )

    LCDReaderStatusBridge(
        reader_path,
        clock=lambda: 100.0,
    ).publish(
        {
            "thread_alive": True,
            "dispatcher_alive": True,
        }
    )

    LCDDisplayStatusBridge(
        display_path,
        clock=lambda: 100.0,
    ).publish(
        [
            "TruePanel",
            "Mission Ready",
        ],
        page="show_mission_home",
        source="runtime",
    )

    service = SnapshotService(
        collector=FakeCollector(),
        config={},
        history_path=(
            tmp_path
            / "history.jsonl"
        ),
        lcd_reader_status_path=(
            reader_path
        ),
        lcd_display_status_path=(
            display_path
        ),
        clock=lambda: 104.0,
    )

    lcd_payload = service.status()[
        "lcd"
    ]
    display = lcd_payload[
        "display"
    ]

    assert lcd_payload[
        "available"
    ] is True
    assert lcd_payload[
        "stale"
    ] is False
    assert display[
        "line1"
    ] == "TruePanel       "
    assert display[
        "line2"
    ] == "Mission Ready   "
    assert display[
        "page"
    ] == "show_mission_home"
    assert display[
        "source"
    ] == "runtime"
    assert display[
        "age_seconds"
    ] == 4.0
    assert display[
        "stale"
    ] is False


def test_status_snapshot_marks_old_lcd_display_stale(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        (
            "truepanel.web.snapshot."
            "get_fan_status"
        ),
        lambda: {},
    )

    display_path = (
        tmp_path
        / "lcd-display-status.json"
    )

    from truepanel.hardware.lcd_display_status_bridge import (
        LCDDisplayStatusBridge,
    )

    LCDDisplayStatusBridge(
        display_path,
        clock=lambda: 100.0,
    ).publish(
        [
            "Old frame",
            "Waiting",
        ]
    )

    service = SnapshotService(
        collector=FakeCollector(),
        config={},
        history_path=(
            tmp_path
            / "history.jsonl"
        ),
        lcd_reader_status_path=(
            tmp_path
            / "missing-reader.json"
        ),
        lcd_display_status_path=(
            display_path
        ),
        clock=lambda: 120.0,
    )

    lcd_payload = service.status()[
        "lcd"
    ]

    assert lcd_payload[
        "available"
    ] is True
    assert lcd_payload[
        "stale"
    ] is True
    assert lcd_payload[
        "display"
    ][
        "stale"
    ] is True


def test_status_snapshot_uses_none_for_missing_display(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        (
            "truepanel.web.snapshot."
            "get_fan_status"
        ),
        lambda: {},
    )

    service = SnapshotService(
        collector=FakeCollector(),
        config={},
        history_path=(
            tmp_path
            / "history.jsonl"
        ),
        lcd_reader_status_path=(
            tmp_path
            / "missing-reader.json"
        ),
        lcd_display_status_path=(
            tmp_path
            / "missing-display.json"
        ),
        clock=lambda: 100.0,
    )

    lcd_payload = service.status()[
        "lcd"
    ]

    assert lcd_payload[
        "available"
    ] is False
    assert lcd_payload[
        "stale"
    ] is True
    assert lcd_payload[
        "display"
    ] is None


def test_lcd_status_does_not_refresh_collector(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        (
            "truepanel.web.snapshot."
            "get_fan_status"
        ),
        lambda: {},
    )

    class CountingCollector:
        def __init__(self):
            self.calls = 0

        def update(self):
            self.calls += 1
            return {}

    collector = CountingCollector()

    service = SnapshotService(
        collector=collector,
        config={},
        history_path=(
            tmp_path
            / "history.jsonl"
        ),
        lcd_reader_status_path=(
            tmp_path
            / "missing-reader.json"
        ),
        lcd_display_status_path=(
            tmp_path
            / "missing-display.json"
        ),
        clock=lambda: 100.0,
    )

    payload = service.lcd_status()

    assert collector.calls == 0
    assert payload["read_only"] is True
    assert payload["lcd"]["available"] is False


def test_status_snapshot_publishes_lcd_transport_diagnostics(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        (
            "truepanel.web.snapshot."
            "get_fan_status"
        ),
        lambda: {},
    )

    lcd_status_path = (
        tmp_path
        / "lcd-reader-status.json"
    )

    from truepanel.hardware.lcd_reader_status_bridge import (
        LCDReaderStatusBridge,
    )

    LCDReaderStatusBridge(
        lcd_status_path,
        clock=lambda: 100.0,
    ).publish(
        {
            "connected": False,
            "connection_error": (
                "PermissionError: permission denied"
            ),
            "port": "/dev/ttyS1",
            "speed": 1200,
            "reader_errors": 2,
            "last_reader_error": (
                "OSError: input/output error"
            ),
        }
    )

    service = SnapshotService(
        collector=FakeCollector(),
        config={},
        history_path=(
            tmp_path
            / "history.jsonl"
        ),
        lcd_reader_status_path=(
            lcd_status_path
        ),
        clock=lambda: 100.0,
    )

    reader = service.lcd_status()[
        "lcd"
    ]["reader"]

    assert reader["connected"] is False
    assert reader["connection_error"] == (
        "PermissionError: permission denied"
    )
    assert reader["port"] == "/dev/ttyS1"
    assert reader["speed"] == 1200
    assert reader["reader_errors"] == 2
    assert reader["last_reader_error"] == (
        "OSError: input/output error"
    )


def test_status_snapshot_uses_safe_transport_defaults(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        (
            "truepanel.web.snapshot."
            "get_fan_status"
        ),
        lambda: {},
    )

    service = SnapshotService(
        collector=FakeCollector(),
        config={},
        history_path=(
            tmp_path
            / "history.jsonl"
        ),
        lcd_reader_status_path=(
            tmp_path
            / "missing-lcd-status.json"
        ),
        clock=lambda: 100.0,
    )

    reader = service.lcd_status()[
        "lcd"
    ]["reader"]

    assert reader["connected"] is False
    assert reader["connection_error"] is None
    assert reader["port"] is None
    assert reader["speed"] == 0


def test_network_payload_accepts_collector_rate_shape():
    payload = SnapshotService._network_payload(
        {
            "network": {
                "enp116s0": {
                    "download_mb": 12.3,
                    "upload_mb": 1.7,
                },
                "tailscale0": {
                    "download_mb": 0.1,
                    "upload_mb": 0.0,
                },
            }
        }
    )

    assert payload == [
        {
            "name": "enp116s0",
            "download_mb": 12.3,
            "upload_mb": 1.7,
        },
        {
            "name": "tailscale0",
            "download_mb": 0.1,
            "upload_mb": 0.0,
        },
    ]


def test_network_payload_preserves_legacy_address_shape():
    payload = SnapshotService._network_payload(
        {
            "interfaces": {
                "eth0": "192.168.0.10",
            }
        }
    )

    assert payload == [
        {
            "name": "eth0",
            "address": "192.168.0.10",
        }
    ]


def test_network_payload_preserves_friendly_interface_metadata():
    payload = SnapshotService._network_payload(
        {
            "network": {
                "enp116s0": {
                    "position": 2,
                    "label": "Ethernet Port 2",
                    "address": "192.168.0.108",
                    "primary": True,
                    "kind": "lan",
                }
            }
        }
    )

    assert payload == [
        {
            "name": "enp116s0",
            "position": 2,
            "label": "Ethernet Port 2",
            "address": "192.168.0.108",
            "primary": True,
            "kind": "lan",
        }
    ]


def test_network_payload_preserves_friendly_interface_metadata():
    payload = SnapshotService._network_payload(
        {
            "network": {
                "enp116s0": {
                    "position": 2,
                    "label": "Ethernet Port 2",
                    "address": "192.168.0.108",
                    "primary": True,
                    "kind": "lan",
                }
            }
        }
    )

    assert payload == [
        {
            "name": "enp116s0",
            "position": 2,
            "label": "Ethernet Port 2",
            "address": "192.168.0.108",
            "primary": True,
            "kind": "lan",
        }
    ]
