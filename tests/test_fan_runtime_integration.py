from pathlib import Path


def test_lcd_runtime_builds_fan_control_runtime():
    source = Path(
        "lcd-menu.py"
    ).read_text()

    assert (
        "build_fan_control_runtime"
        in source
    )

    assert (
        "fan_control_runtime = "
        "build_fan_control_runtime("
        in source
    )


def test_lcd_runtime_publishes_runtime_status():
    source = Path(
        "lcd-menu.py"
    ).read_text()

    assert (
        "fan_control_runtime"
        ".status_payload()"
        in source.replace(
            "\n",
            "",
        ).replace(
            " ",
            "",
        )
    )


def test_lcd_runtime_shuts_down_fan_control():
    source = Path(
        "lcd-menu.py"
    ).read_text()

    assert (
        "fan_control_runtime.shutdown()"
        in source
    )


def test_fan_history_uses_post_transition_telemetry():
    source = Path(
        "lcd-menu.py"
    ).read_text(
        encoding="utf-8",
    )

    assert (
        "post_transition_telemetry = ("
        in source
    )
    assert (
        "fan_command_telemetry(),"
        in source
    )
    assert (
        "decision,\n"
        "            post_transition_telemetry,"
        in source
    )
