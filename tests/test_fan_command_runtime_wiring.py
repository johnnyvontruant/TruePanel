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


def test_command_socket_starts_before_visual_startup():
    text = source()
    main_start = text.index(
        "def main():"
    )

    socket_start = text.index(
        "fan_command_server.start()",
        main_start,
    )
    animation_start = text.index(
        "bay_led_startup_animation.run()",
        main_start,
    )
    splash_start = text.index(
        "show_startup_splash()",
        main_start,
    )
    buzzer_start = text.index(
        "buzzer.startup()",
        main_start,
    )

    assert socket_start < animation_start
    assert socket_start < splash_start
    assert socket_start < buzzer_start


def test_status_publishes_before_command_socket():
    text = source()

    status_publish = text.index(
        "publish_fan_control_status()",
        text.index("def main():"),
    )
    socket_start = text.index(
        "fan_command_server.start()"
    )

    assert status_publish < socket_start
