from pathlib import Path


def source():
    return Path(
        "lcd-menu.py"
    ).read_text(
        encoding="utf-8"
    )


def test_lcd_runtime_uses_host_bootstrap():
    text = source()

    assert (
        "host_bootstrap = "
        "build_host_agent_bootstrap("
        in text
    )

    assert (
        "fan_control_runtime = "
        "host_bootstrap.fan_runtime"
        in text
    )

    assert (
        "host_bootstrap.thermal_authority"
        in text
    )

    assert (
        "host_bootstrap.fan_control_history"
        in text
    )

    assert (
        "host_bootstrap."
        "thermal_commissioning_history"
        in text
    )


def test_lcd_runtime_no_longer_constructs_host_dependencies():
    text = source()

    assert "build_fan_control_runtime(" not in text
    assert "HostThermalAuthority(" not in text

    assert (
        "FanControlHistory("
        not in text
    )

    assert (
        "ThermalCommissioningHistory("
        not in text
    )


def test_thermal_observer_is_host_owned():
    text = source()

    assert (
        "host_bootstrap"
        "\n        .thermal_observer"
        "\n        .observe(telemetry)"
        in text
    )

    for application_owned in (
        "ThermalObserverHistory(",
        "ThermalFanPolicy(",
        "event_from_recommendation(",
        "thermal_observer_last_signature",
        "thermal_observer_previous_profile",
    ):
        assert application_owned not in text


def test_host_bootstrap_owns_history_behavior():
    runtime = source()

    bootstrap = Path(
        "truepanel/host/bootstrap.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "host_bootstrap.record_fan_event("
        in runtime
    )

    assert (
        "host_bootstrap.record_commissioning_event("
        in runtime
    )

    assert (
        "host_bootstrap.fan_event_source("
        in runtime
    )

    assert (
        "fan_control_history.append("
        not in runtime
    )

    assert (
        "thermal_commissioning_history.append("
        not in runtime
    )

    assert "event_from_decision(" in bootstrap
    assert "commissioning_event(" in bootstrap

    assert (
        "fan_control_history.append("
        in bootstrap
    )

    assert (
        "thermal_commissioning_history.append("
        in bootstrap
    )


def test_automatic_restoration_has_no_lcd_hardware_fallback():
    runtime = source()

    start = runtime.index(
        "def restore_motherboard_fan_control("
    )

    end = runtime.index(
        "\ndef ",
        start + 1,
    )

    block = runtime[start:end]

    assert (
        ".safety"
        in block
    )

    assert (
        ".restore_automatic("
        in block
    )

    assert (
        ".request_profile("
        not in block
    )


def test_lcd_uses_host_owned_telemetry_normalizer():
    runtime = source()

    bootstrap = Path(
        "truepanel/host/bootstrap.py"
    ).read_text(
        encoding="utf-8"
    )

    host_provider = Path(
        "truepanel/host/telemetry.py"
    ).read_text(
        encoding="utf-8"
    )

    hardware_provider = Path(
        "truepanel/hardware/drive_temperatures.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "DriveTemperatureProvider"
        not in runtime
    )

    assert (
        "HostFanTelemetryProvider"
        not in runtime
    )

    assert (
        "DriveTemperatureProvider"
        in bootstrap
    )

    assert (
        "HostFanTelemetryProvider"
        in bootstrap
    )

    assert (
        "telemetry=telemetry"
        in bootstrap
    )

    start = runtime.index(
        "def fan_command_telemetry("
    )

    end = runtime.index(
        "\ndef ",
        start + 1,
    )

    block = runtime[start:end]

    assert (
        "host_bootstrap"
        in block
    )

    assert (
        ".telemetry"
        in block
    )

    assert ".snapshot()" in block

    assert "get_state(" not in block

    assert (
        "class HostFanTelemetryProvider"
        in host_provider
    )

    assert (
        "class DriveTemperatureProvider"
        in hardware_provider
    )


def test_lcd_uses_host_owned_status_publisher():
    runtime = source()

    bootstrap = Path(
        "truepanel/host/bootstrap.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "FanControlStatusBridge" not in runtime
    assert "publish_host_fan_status" not in runtime
    assert "FanControlStatusBridge" in bootstrap
    assert "publish_host_fan_status" in bootstrap

    publisher_start = runtime.index(
        "def publish_fan_control_status("
    )
    publisher_end = runtime.index(
        "\ndef fan_command_telemetry(",
        publisher_start,
    )
    publisher = runtime[publisher_start:publisher_end]

    assert "host_bootstrap.publish_fan_status(" in publisher
    assert "fan_control_runtime.status_payload()" not in publisher
    assert "fan_control_status_bridge.publish(" not in publisher
