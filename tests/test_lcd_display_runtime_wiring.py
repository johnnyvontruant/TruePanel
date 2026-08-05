from pathlib import Path


def test_runtime_observes_all_complete_lcd_frames():
    driver = Path(
        "qnaplcd/__init__.py"
    ).read_text(
        encoding="utf-8",
    )
    runtime = Path(
        "lcd-menu.py"
    ).read_text(
        encoding="utf-8",
    )

    assert "def set_frame_handler(" in driver
    assert "_notify_frame_handler(" in driver
    assert "if written:" in driver

    assert "lcd.set_frame_handler(" in runtime
    assert "publish_lcd_display(" in runtime


def test_frame_observer_does_not_own_serial_transport():
    source = Path(
        "truepanel/hardware/"
        "lcd_display_status_bridge.py"
    ).read_text(
        encoding="utf-8",
    )

    assert "serial.Serial" not in source
    assert "/dev/ttyS1" not in source
