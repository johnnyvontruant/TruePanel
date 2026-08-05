from pathlib import Path


def test_lcd_command_server_is_wired_into_runtime():
    source = Path(
        "lcd-menu.py"
    ).read_text(
        encoding="utf-8",
    )

    assert "LCDCommandProcessor" in source
    assert "LCDCommandServer" in source
    assert "def build_lcd_command_server():" in source
    assert "lcd.submit_button_event(" in source
    assert "lcd_command_server.start()" in source
    assert "lcd_command_server.stop()" in source


def test_virtual_commands_do_not_write_raw_serial():
    source = Path(
        "truepanel/hardware/lcd_command.py"
    ).read_text(
        encoding="utf-8",
    )

    assert "serial.Serial" not in source
    assert "encode_query" not in source
    assert "encode_display_write" not in source
