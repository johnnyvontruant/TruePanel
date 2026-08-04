from pathlib import Path


def test_web_lcd_route_uses_guarded_client():
    source = Path(
        "truepanel/web/server.py"
    ).read_text(
        encoding="utf-8",
    )

    assert (
        '"/api/v1/lcd/button"'
        in source
    )
    assert "LCDCommandClient" in source
    assert (
        ".lcd_command_client"
        in source
    )


def test_web_server_does_not_import_qnaplcd():
    source = Path(
        "truepanel/web/server.py"
    ).read_text(
        encoding="utf-8",
    )

    assert "import qnaplcd" not in source
    assert "/dev/ttyS1" not in source
    assert "serial.Serial" not in source
