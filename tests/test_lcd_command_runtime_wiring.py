from pathlib import Path


def test_virtual_commands_do_not_write_raw_serial():
    source = Path(
        "truepanel/hardware/lcd_command.py"
    ).read_text(
        encoding="utf-8",
    )

    assert "serial.Serial" not in source
    assert "encode_query" not in source
    assert "encode_display_write" not in source
