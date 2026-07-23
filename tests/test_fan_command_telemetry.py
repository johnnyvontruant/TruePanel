from pathlib import Path


def test_fan_command_telemetry_accepts_temp_key():
    text = Path(
        "lcd-menu.py"
    ).read_text()

    assert '''item.get(
                    "temp"
                )''' in text
