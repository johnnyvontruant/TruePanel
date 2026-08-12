from pathlib import Path


def test_fan_command_telemetry_uses_shared_hardware_temperature_provider():
    runtime = Path(
        "lcd-menu.py"
    ).read_text(
        encoding="utf-8"
    )

    bootstrap = Path(
        "truepanel/host/bootstrap.py"
    ).read_text(
        encoding="utf-8"
    )

    hardware_provider = Path(
        "truepanel/hardware/drive_temperatures.py"
    ).read_text(
        encoding="utf-8"
    )

    host_provider = Path(
        "truepanel/host/telemetry.py"
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
        "drive_temperature_provider_factory"
        in bootstrap
    )

    assert (
        "telemetry_factory=HostFanTelemetryProvider"
        in bootstrap
    )

    assert (
        "temperature_provider=("
        in bootstrap
    )

    assert (
        "class DriveTemperatureProvider"
        in hardware_provider
    )

    assert (
        "parse_legacy_smart_temperature"
        in hardware_provider
    )

    assert (
        "class HostFanTelemetryProvider"
        in host_provider
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
