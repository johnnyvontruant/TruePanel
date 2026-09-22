from pathlib import Path

from truepanel.config.loader import DEFAULT_CONFIG, load_config
from truepanel.mission_control.constants import Priority
from truepanel.mission_control.watchers.storage_health import (
    StorageHealthWatcher,
    build_storage_health_watcher,
    get_storage_health_config,
)


def device(
    *,
    state="healthy",
    message="healthy",
    pending=0,
):
    return {
        "device": "sdc",
        "device_path": "/dev/sdc",
        "serial": "SERIAL-3",
        "label": "Bay 3",
        "state": state,
        "message": message,
        "temperature_c": 40,
        "telemetry": {
            "temperature_c": 40,
            "reallocated_sectors": 0,
            "pending_sectors": pending,
            "offline_uncorrectable": pending,
            "interface_errors": 0,
        },
    }


def report(*devices):
    return {
        "device_count": len(devices),
        "devices": list(devices),
    }


def test_default_config_enables_storage_health():
    settings = DEFAULT_CONFIG["mission_control"]["storage_health"]

    assert settings["enabled"] is True
    assert settings["interval"] == 300
    assert settings["emit_initial_conditions"] is True
    assert settings["record_events"] is True


def test_factory_returns_none_when_disabled():
    config = {
        "mission_control": {
            "storage_health": {
                "enabled": False,
            },
        },
    }

    watcher = build_storage_health_watcher(config)

    assert watcher is None


def test_factory_builds_configured_watcher(tmp_path):
    log_path = tmp_path / "events.jsonl"

    config = {
        "mission_control": {
            "storage_health": {
                "enabled": True,
                "interval": 42,
                "emit_initial_conditions": False,
                "record_events": True,
                "event_log": str(log_path),
            },
        },
    }

    watcher = build_storage_health_watcher(
        config,
        report_provider=lambda: report(device()),
    )

    assert isinstance(watcher, StorageHealthWatcher)
    assert watcher.interval == 42
    assert watcher.emit_initial_conditions is False
    assert watcher.recorder is not None
    assert watcher.recorder.path == log_path


def test_factory_can_disable_event_recording():
    config = {
        "mission_control": {
            "storage_health": {
                "record_events": False,
            },
        },
    }

    watcher = build_storage_health_watcher(
        config,
        report_provider=lambda: report(device()),
    )

    assert watcher is not None
    assert watcher.recorder is None


def test_factory_watcher_emits_initial_hardware_condition():
    config = {
        "mission_control": {
            "storage_health": {
                "interval": 0,
                "record_events": False,
            },
        },
    }

    watcher = build_storage_health_watcher(
        config,
        report_provider=lambda: report(
            device(
                state="critical",
                message="pending sectors: 1608",
                pending=1608,
            )
        ),
    )

    event = watcher(None)

    assert event is not None
    assert event.priority == Priority.CRITICAL
    assert event.title == "Drive Critical"
    assert event.message == "pending sectors: 1608"


def test_partial_config_retains_defaults():
    settings = get_storage_health_config(
        {
            "mission_control": {
                "storage_health": {
                    "interval": 60,
                },
            },
        }
    )

    assert settings["interval"] == 60
    assert settings["enabled"] is True
    assert settings["record_events"] is True


def test_project_yaml_loads_storage_health_configuration():
    config = load_config("truepanel.yaml")
    settings = config["mission_control"]["storage_health"]

    assert settings["enabled"] is True
    assert settings["interval"] == 300
    assert settings["emit_initial_conditions"] is True
    assert settings["record_events"] is True
    assert settings["event_log"] == (
        "/var/lib/truepanel/storage/events.jsonl"
    )


def test_runtime_launcher_contains_registration():
    source = Path("lcd-menu.py").read_text(encoding="utf-8")

    assert "build_storage_health_watcher(config)" in source
    assert "mission.register(storage_health_watcher)" in source


def test_storage_health_default_hysteresis_thresholds():
    settings = get_storage_health_config({})

    assert settings["warning_temperature_recovery_c"] == 42
    assert settings["critical_temperature_recovery_c"] == 52


def test_storage_health_custom_hysteresis_thresholds():
    config = {
        "mission_control": {
            "storage_health": {
                "warning_temperature_recovery_c": 41,
                "critical_temperature_recovery_c": 51,
            }
        }
    }

    watcher = build_storage_health_watcher(
        config,
        report_provider=lambda: {"devices": []},
    )

    assert watcher is not None
    assert watcher.differ.warning_temperature_recovery_c == 41
    assert watcher.differ.critical_temperature_recovery_c == 51


def test_no_startup_led_clear_when_initial_conditions_suppressed():
    from types import SimpleNamespace

    from truepanel.hardware.bay_leds import TVS671BayLedController

    commands = []
    controller = TVS671BayLedController(command_writer=commands.append)
    config = {
        "mission_control": {
            "storage_health": {
                "bay_leds_enabled": True,
                "bay_leds_clear_on_start": True,
                "emit_initial_conditions": False,
                "record_events": False,
                "interval": 0,
            }
        }
    }

    watcher = build_storage_health_watcher(
        config,
        manager=SimpleNamespace(bay_leds=controller),
        report_provider=lambda: report({
            **device(
                state="critical",
                message="pending sectors: 1608",
                pending=1608,
            ),
            "physical_bay": 3,
        }),
    )
    assert watcher is not None

    # Construction must not erase a previously asserted critical LED.
    assert commands == []
    assert watcher(None) is None
    # The first fresh critical snapshot reasserts Bay 3's steady-red channel.
    assert commands == [0x86]
    assert 0x87 not in commands
