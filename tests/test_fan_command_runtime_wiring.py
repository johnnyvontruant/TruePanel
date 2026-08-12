from pathlib import Path


def source():
    return Path(
        "lcd-menu.py"
    ).read_text(
        encoding="utf-8"
    )



def test_lcd_builds_command_telemetry():
    runtime = source()

    provider = Path(
        "truepanel/host/telemetry.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "def fan_command_telemetry():"
        in runtime
    )

    assert (
        "HostFanTelemetryProvider("
        in runtime
    )

    assert (
        "fan_status_provider=("
        in runtime
    )

    assert (
        "get_fan_status"
        in runtime
    )

    assert (
        '"fan_status": dict('
        in provider
    )

    assert (
        "self._fan_status_provider()"
        in provider
    )

def test_lcd_publishes_observe_only_thermal_policy():
    runtime = source()

    status = Path(
        "truepanel/host/status.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "ThermalFanPolicy" in runtime
    assert (
        "def observe_thermal_fan_policy("
        in runtime
    )

    assert (
        "publish_host_fan_status("
        in runtime
    )

    assert (
        '"thermal_policy_mode"'
        in status
    )
    assert '"thermal_recommended_profile"' in status
    assert "observe_thermal_fan_policy()" in runtime


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
