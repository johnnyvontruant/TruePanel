from pathlib import Path


def source():
    return Path(
        "lcd-menu.py"
    ).read_text(
        encoding="utf-8"
    )


def test_lcd_imports_command_server():
    text = source()

    assert (
        "FanCommandProcessor"
        in text
    )
    assert (
        "FanCommandServer"
        in text
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


def test_lcd_starts_command_server():
    text = source()

    assert (
        "fan_command_server = ("
        in text
    )
    assert (
        "build_fan_command_server()"
        in text
    )
    assert (
        "fan_command_server.start()"
        in text
    )


def test_lcd_stops_socket_before_runtime():
    text = source()

    socket_stop = text.index(
        "fan_command_server.stop()"
    )
    runtime_stop = text.index(
        "fan_control_runtime.shutdown()"
    )

    assert socket_stop < runtime_stop


def test_disabled_runtime_does_not_build_socket():
    text = source()

    assert (
        "if not fan_control_runtime.enabled:"
        in text
    )
    assert (
        "return None"
        in text
    )
