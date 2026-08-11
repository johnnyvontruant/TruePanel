from pathlib import Path


def source():
    return Path(
        "lcd-menu.py"
    ).read_text(
        encoding="utf-8"
    )


def test_lcd_command_server_is_wired_into_host_agent():
    text = source()

    assert "LCDCommandProcessor" in text
    assert "LCDCommandServer" in text
    assert "def build_lcd_command_server():" in text
    assert "lcd.submit_button_event(" in text

    assert (
        "lcd_server_factory=("
        in text
    )

    assert (
        "build_lcd_command_server"
        in text
    )

    assert (
        "host_agent_runtime.start()"
        in text
    )

    assert (
        "host_agent_runtime.shutdown()"
        in text
    )


def test_virtual_commands_do_not_write_raw_serial():
    text = Path(
        "truepanel/hardware/lcd_command.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "serial.Serial" not in text
    assert "encode_query" not in text
    assert "encode_display_write" not in text
