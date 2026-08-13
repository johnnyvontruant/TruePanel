from pathlib import Path


def source():
    return Path(
        "lcd-menu.py"
    ).read_text(
        encoding="utf-8"
    )


def test_lcd_routes_host_telemetry_through_runtime():
    runtime = source()
    bootstrap = Path(
        "truepanel/host/bootstrap.py"
    ).read_text(encoding="utf-8")
    host_runtime = Path(
        "truepanel/host/runtime.py"
    ).read_text(encoding="utf-8")
    provider = Path(
        "truepanel/host/telemetry.py"
    ).read_text(encoding="utf-8")

    assert "def fan_command_telemetry():" not in runtime
    assert "HostFanTelemetryProvider(" not in runtime
    assert "HostFanTelemetryProvider" in bootstrap
    assert "fan_status_provider=get_fan_status" in bootstrap
    assert "def fan_telemetry(" in host_runtime
    assert "return self._safety.telemetry()" in host_runtime
    assert '"fan_status": dict(' in provider
    assert "self._fan_status_provider()" in provider


def test_lcd_routes_thermal_observation_and_status_through_runtime():
    runtime = source()
    bootstrap = Path(
        "truepanel/host/bootstrap.py"
    ).read_text(encoding="utf-8")
    host_runtime = Path(
        "truepanel/host/runtime.py"
    ).read_text(encoding="utf-8")
    reconciliation = Path(
        "truepanel/host/reconciliation.py"
    ).read_text(encoding="utf-8")
    status = Path(
        "truepanel/host/status.py"
    ).read_text(encoding="utf-8")

    assert "ThermalFanPolicy" not in runtime
    assert "ThermalFanPolicy" in bootstrap
    assert "def observe_thermal_fan_policy(" in runtime
    assert "host_agent_runtime.observe_thermal(" in runtime
    assert ".thermal_observer" not in runtime
    assert "def observe(" in reconciliation
    assert "def observe_thermal(" in host_runtime
    assert "def publish_fan_status(" in host_runtime
    assert "def service_cycle(" in host_runtime
    assert "host_agent_runtime.publish_fan_status(" in runtime
    assert "host_agent_runtime.service_cycle(" in runtime
    assert "publish_host_fan_status" in bootstrap
    assert '"thermal_policy_mode"' in status
    assert '"thermal_recommended_profile"' in status


def test_observer_does_not_request_profiles():
    text = source()

    observer_start = text.index(
        "def observe_thermal_fan_policy("
    )
    observer_end = text.index(
        "\ndef ",
        observer_start + 1,
    )
    observer = text[
        observer_start:observer_end
    ]

    assert "request_profile(" not in observer
    assert "service.tick(" not in observer
    assert "executor" not in observer
