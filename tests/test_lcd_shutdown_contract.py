from pathlib import Path


def test_lcd_runtime_publishes_status_after_close():
    source = Path(
        "lcd-menu.py"
    ).read_text(
        encoding="utf-8"
    )

    shutdown = source.rsplit(
        "lcd.close()",
        1,
    )[1]

    assert "publish_lcd_reader_status()" in shutdown


def test_planned_stop_signal_comes_from_driver_snapshot():
    source = Path(
        "qnaplcd/__init__.py"
    ).read_text(
        encoding="utf-8"
    )

    assert '"stop_requested": (' in source
    assert "self.stop_event.is_set()" in source
    assert "self.stop_event.set()" in source
