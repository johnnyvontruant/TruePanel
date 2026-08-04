import json

from truepanel.hardware.lcd_reader_status_bridge import (
    LCDReaderStatusBridge,
)


class FakeClock:
    def __init__(self, value=100.0):
        self.value = float(value)

    def __call__(self):
        return self.value


def test_bridge_publishes_and_reads_reader_health(
    tmp_path,
):
    clock = FakeClock()
    path = tmp_path / "lcd-reader-status.json"

    bridge = LCDReaderStatusBridge(
        path,
        clock=clock,
    )

    published = bridge.publish(
        {
            "thread_alive": True,
            "replies": 12,
            "button_reports": 3,
            "last_button_mask": 0,
            "last_pressed_button_mask": 2,
            "callback_count": 3,
            "callback_errors": 0,
            "max_callback_duration_ms": 4.25,
        }
    )

    assert published["timestamp"] == 100.0

    payload = bridge.read()

    assert payload is not None
    assert payload["age_seconds"] == 0.0
    assert payload["reader"]["thread_alive"] is True
    assert payload["reader"]["replies"] == 12
    assert payload["reader"]["button_reports"] == 3
    assert payload["reader"]["last_button_mask"] == 0
    assert (
        payload["reader"][
            "last_pressed_button_mask"
        ]
        == 2
    )
    assert payload["reader"]["callback_errors"] == 0


def test_bridge_replaces_file_atomically(
    tmp_path,
):
    clock = FakeClock()
    path = tmp_path / "lcd-reader-status.json"

    bridge = LCDReaderStatusBridge(
        path,
        clock=clock,
    )

    bridge.publish(
        {
            "replies": 1,
        }
    )

    first_inode = path.stat().st_ino

    clock.value = 101.0

    bridge.publish(
        {
            "replies": 2,
        }
    )

    second_inode = path.stat().st_ino

    assert first_inode != second_inode
    assert json.loads(
        path.read_text()
    )["reader"]["replies"] == 2


def test_bridge_rejects_stale_status(
    tmp_path,
):
    clock = FakeClock()
    bridge = LCDReaderStatusBridge(
        tmp_path / "lcd-reader-status.json",
        clock=clock,
    )

    bridge.publish(
        {
            "thread_alive": True,
        }
    )

    clock.value += 16.0

    assert bridge.read(
        max_age=15.0
    ) is None


def test_bridge_rejects_invalid_json(
    tmp_path,
):
    path = tmp_path / "lcd-reader-status.json"
    path.write_text(
        "not-json"
    )

    bridge = LCDReaderStatusBridge(path)

    assert bridge.read() is None


def test_bridge_normalizes_reader_values(
    tmp_path,
):
    bridge = LCDReaderStatusBridge(
        tmp_path / "lcd-reader-status.json",
        clock=lambda: 100.0,
    )

    bridge.publish(
        {
            "replies": "8",
            "reader_errors": -4,
            "button_reports": None,
            "callback_errors": "2",
            "last_reader_error": RuntimeError(
                "serial failed"
            ),
        }
    )

    payload = bridge.read()

    assert payload is not None
    reader = payload["reader"]

    assert reader["replies"] == 8
    assert reader["reader_errors"] == 0
    assert reader["button_reports"] == 0
    assert reader["callback_errors"] == 2
    assert (
        reader["last_reader_error"]
        == "serial failed"
    )
