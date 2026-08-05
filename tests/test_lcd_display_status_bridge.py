from truepanel.hardware.lcd_display_status_bridge import (
    LCDDisplayStatusBridge,
)


def test_display_bridge_publishes_two_padded_lines(
    tmp_path,
):
    now = [100.0]
    bridge = LCDDisplayStatusBridge(
        tmp_path / "lcd-display.json",
        clock=lambda: now[0],
    )

    payload = bridge.publish(
        [
            "CPU 14%",
            "RAM 31%",
        ],
        page="show_cpu_ram",
        source="hardware",
    )

    assert payload["display"]["line1"] == (
        "CPU 14%         "
    )
    assert payload["display"]["line2"] == (
        "RAM 31%         "
    )
    assert payload["display"]["page"] == (
        "show_cpu_ram"
    )


def test_display_bridge_reads_fresh_snapshot(
    tmp_path,
):
    now = [100.0]
    bridge = LCDDisplayStatusBridge(
        tmp_path / "lcd-display.json",
        clock=lambda: now[0],
    )

    bridge.publish(
        [
            "TruePanel",
            "Mission Ready",
        ]
    )

    now[0] = 105.0
    status = bridge.read(
        max_age=10.0
    )

    assert status is not None
    assert status["stale"] is False
    assert status["age_seconds"] == 5.0


def test_display_bridge_marks_old_snapshot_stale(
    tmp_path,
):
    now = [100.0]
    bridge = LCDDisplayStatusBridge(
        tmp_path / "lcd-display.json",
        clock=lambda: now[0],
    )

    bridge.publish(
        [
            "TruePanel",
            "Mission Ready",
        ]
    )

    now[0] = 120.0
    status = bridge.read(
        max_age=10.0
    )

    assert status is not None
    assert status["stale"] is True


def test_display_bridge_returns_none_for_missing_file(
    tmp_path,
):
    bridge = LCDDisplayStatusBridge(
        tmp_path / "missing.json"
    )

    assert bridge.read() is None
