from pathlib import Path


def source():
    return Path(
        "lcd-menu.py"
    ).read_text(
        encoding="utf-8"
    )


def test_lcd_builds_command_telemetry():
    text = source()

    assert (
        "def fan_command_telemetry():"
        in text
    )
    assert (
        '"fan_status": get_fan_status()'
        in text
    )
    assert (
        '"temperatures_c": tuple('
        in text
    )
    assert (
        '"telemetry_fresh":'
        in text
    )


def test_lcd_publishes_observe_only_thermal_policy():
    text = source()

    assert "ThermalFanPolicy" in text
    assert "def observe_thermal_fan_policy(" in text
    assert '"thermal_policy_mode"' in text
    assert '"thermal_recommended_profile"' in text
    assert "observe_thermal_fan_policy()" in text


def test_observer_does_not_request_profiles():
    text = source()

    observer_start = text.index(
        "def observe_thermal_fan_policy("
    )
    observer_end = text.index(
        "def record_fan_control_event(",
        observer_start,
    )
    observer = text[
        observer_start:observer_end
    ]

    assert "request_profile(" not in observer
    assert "service.tick(" not in observer
    assert "executor" not in observer
