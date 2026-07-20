from truepanel.mission_control.constants import (
    Category,
    Priority,
)
from truepanel.mission_control.watchers.fan_health import (
    FanHealthWatcher,
    build_fan_health_watcher,
    get_fan_channel_config,
    get_fan_health_config,
)


def status(
    fan1=1500,
    fan2=1450,
    fan3=0,
):
    return {
        "fan_channels": [
            {
                "number": 1,
                "rpm": fan1,
            },
            {
                "number": 2,
                "rpm": fan2,
            },
            {
                "number": 3,
                "rpm": fan3,
            },
        ]
    }


CHANNELS = {
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


def test_healthy_fans_are_silent():
    watcher = FanHealthWatcher(
        status_provider=lambda: status(),
        channels=CHANNELS,
        interval=0,
    )

    assert watcher(None) is None


def test_unused_header_is_ignored():
    watcher = FanHealthWatcher(
        status_provider=lambda: status(
            fan3=0,
        ),
        channels=CHANNELS,
        interval=0,
        consecutive_failures=1,
        emit_initial_conditions=True,
    )

    assert watcher(None) is None
    assert 3 not in watcher.failed_channels


def test_low_rpm_is_debounced():
    watcher = FanHealthWatcher(
        status_provider=lambda: status(
            fan1=0,
        ),
        channels=CHANNELS,
        interval=0,
        minimum_rpm=300,
        consecutive_failures=3,
        emit_initial_conditions=True,
    )

    assert watcher(None) is None
    assert watcher(None) is None

    event = watcher(None)

    assert event.priority == Priority.WARNING
    assert event.category == Category.THERMAL
    assert event.title == "FAN ALERT"
    assert event.message == "Rear Fan 1 0 RPM"
    assert event.event_id == (
        "thermal.fan1.low_rpm"
    )
    assert event.metadata["channel"] == 1
    assert event.metadata["minimum_rpm"] == 300


def test_failed_fan_alert_is_not_repeated():
    watcher = FanHealthWatcher(
        status_provider=lambda: status(
            fan1=0,
        ),
        channels=CHANNELS,
        interval=0,
        consecutive_failures=1,
        emit_initial_conditions=True,
    )

    assert watcher(None) is not None
    assert watcher(None) is None
    assert watcher(None) is None


def test_recovery_is_emitted_once():
    reports = iter(
        [
            status(fan1=0),
            status(fan1=1500),
            status(fan1=1500),
        ]
    )

    watcher = FanHealthWatcher(
        status_provider=lambda: next(
            reports
        ),
        channels=CHANNELS,
        interval=0,
        consecutive_failures=1,
        emit_initial_conditions=True,
    )

    failed = watcher(None)
    recovered = watcher(None)
    quiet = watcher(None)

    assert failed.priority == Priority.WARNING
    assert recovered.priority == Priority.HEALTHY
    assert recovered.title == "FAN RECOVERED"
    assert recovered.message == (
        "Rear Fan 1 1500 RPM"
    )
    assert recovered.event_id == (
        "thermal.fan1.recovered"
    )
    assert quiet is None


def test_initial_failure_can_be_suppressed():
    watcher = FanHealthWatcher(
        status_provider=lambda: status(
            fan1=0,
        ),
        channels=CHANNELS,
        interval=0,
        consecutive_failures=1,
        emit_initial_conditions=False,
    )

    assert watcher(None) is None
    assert 1 in watcher.failed_channels


def test_factory_returns_none_when_disabled():
    watcher = build_fan_health_watcher(
        {
            "mission_control": {
                "fan_health": {
                    "enabled": False,
                }
            }
        }
    )

    assert watcher is None


def test_factory_uses_configured_channels():
    config = {
        "hardware": {
            "fans": {
                "channels": CHANNELS,
            }
        },
        "mission_control": {
            "fan_health": {
                "enabled": True,
                "interval": 42,
                "minimum_rpm": 400,
                "consecutive_failures": 4,
                "emit_initial_conditions": True,
            }
        },
    }

    watcher = build_fan_health_watcher(
        config,
        status_provider=lambda: status(),
    )

    assert watcher.interval == 42
    assert watcher.minimum_rpm == 400
    assert watcher.consecutive_failures == 4
    assert watcher.emit_initial_conditions is True
    assert watcher.channels[3]["monitored"] is False


def test_partial_config_retains_defaults():
    settings = get_fan_health_config(
        {
            "mission_control": {
                "fan_health": {
                    "minimum_rpm": 500,
                }
            }
        }
    )

    assert settings["minimum_rpm"] == 500
    assert settings["interval"] == 10
    assert settings["consecutive_failures"] == 3


def test_string_channel_keys_are_normalized():
    channels = get_fan_channel_config(
        {
            "hardware": {
                "fans": {
                    "channels": {
                        "1": {
                            "label": "Rear Fan 1",
                            "monitored": True,
                        }
                    }
                }
            }
        }
    )

    assert channels == {
        1: {
            "label": "Rear Fan 1",
            "monitored": True,
        }
    }


def test_debounced_initial_failure_is_suppressed():
    watcher = FanHealthWatcher(
        status_provider=lambda: status(
            fan1=0,
        ),
        channels=CHANNELS,
        interval=0,
        consecutive_failures=3,
        emit_initial_conditions=False,
    )

    assert watcher(None) is None
    assert watcher(None) is None
    assert watcher(None) is None
    assert watcher(None) is None

    assert 1 in watcher.failed_channels
