from pathlib import Path


def test_fan_command_telemetry_uses_shared_hardware_temperature_provider():
    runtime = Path(
        "lcd-menu.py"
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
        in runtime
    )

    assert (
        "host_drive_temperature_provider = ("
        in runtime
    )

    assert (
        "DriveTemperatureProvider()"
        in runtime
    )

    assert (
        "HostFanTelemetryProvider("
        in runtime
    )

    assert (
        "temperature_provider=("
        in runtime
    )

    assert (
        "host_drive_temperature_provider"
        in runtime
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
        "host_fan_telemetry_provider"
        in block
    )

    assert ".snapshot()" in block

    assert "get_state(" not in block
