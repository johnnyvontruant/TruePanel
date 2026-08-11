from pathlib import Path



def test_fan_command_telemetry_accepts_temp_key():
    provider = Path(
        "truepanel/host/telemetry.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        'item.get(\n'
        '                        "temp"\n'
        '                    )'
        in provider
    )

