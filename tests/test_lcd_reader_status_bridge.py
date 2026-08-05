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
            "dispatcher_alive": True,
            "dispatcher_events": 5,
            "dispatch_queue_depth": 1,
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
    assert payload["reader"]["dispatcher_alive"] is True
    assert payload["reader"]["dispatcher_events"] == 5
    assert payload["reader"]["dispatch_queue_depth"] == 1
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


def test_bridge_publishes_transport_diagnostics(
    tmp_path,
):
    bridge = LCDReaderStatusBridge(
        tmp_path / "lcd-reader-status.json",
        clock=lambda: 100.0,
    )

    bridge.publish(
        {
            "connected": True,
            "connection_error": None,
            "port": "/dev/ttyS1",
            "speed": 1200,
        }
    )

    payload = bridge.read()

    assert payload is not None
    reader = payload["reader"]

    assert reader["connected"] is True
    assert reader["connection_error"] is None
    assert reader["port"] == "/dev/ttyS1"
    assert reader["speed"] == 1200


def test_bridge_normalizes_transport_diagnostics(
    tmp_path,
):
    bridge = LCDReaderStatusBridge(
        tmp_path / "lcd-reader-status.json",
        clock=lambda: 100.0,
    )

    bridge.publish(
        {
            "connected": 1,
            "connection_error": PermissionError(
                "permission denied"
            ),
            "port": 123,
            "speed": "-1",
        }
    )

    payload = bridge.read()

    assert payload is not None
    reader = payload["reader"]

    assert reader["connected"] is True
    assert reader["connection_error"] == (
        "permission denied"
    )
    assert reader["port"] == "123"
    assert reader["speed"] == 0


def test_bridge_tracks_initial_healthy_episode(
    tmp_path,
):
    clock = FakeClock()
    bridge = LCDReaderStatusBridge(
        tmp_path / "lcd-reader-status.json",
        clock=clock,
    )

    payload = bridge.publish(
        {
            "connected": True,
            "thread_alive": True,
            "dispatcher_alive": True,
        }
    )

    reader = payload["reader"]

    assert reader["healthy"] is True
    assert reader["last_healthy_at"] == 100.0
    assert reader["recovery_count"] == 0
    assert reader["last_recovery_at"] is None
    assert reader["episode_state"] == "healthy"
    assert reader["episode_started_at"] == 100.0


def test_bridge_tracks_disconnect_and_recovery(
    tmp_path,
):
    clock = FakeClock()
    bridge = LCDReaderStatusBridge(
        tmp_path / "lcd-reader-status.json",
        clock=clock,
    )

    bridge.publish(
        {
            "connected": True,
            "thread_alive": True,
            "dispatcher_alive": True,
        }
    )

    clock.value = 110.0

    disconnected = bridge.publish(
        {
            "connected": False,
            "thread_alive": True,
            "dispatcher_alive": True,
        }
    )["reader"]

    assert disconnected["healthy"] is False
    assert disconnected["last_healthy_at"] == 100.0
    assert disconnected["recovery_count"] == 0
    assert disconnected["last_recovery_at"] is None
    assert disconnected["episode_state"] == "degraded"
    assert disconnected["episode_started_at"] == 110.0

    clock.value = 120.0

    recovered = bridge.publish(
        {
            "connected": True,
            "thread_alive": True,
            "dispatcher_alive": True,
        }
    )["reader"]

    assert recovered["healthy"] is True
    assert recovered["last_healthy_at"] == 120.0
    assert recovered["recovery_count"] == 1
    assert recovered["last_recovery_at"] == 120.0
    assert recovered["episode_state"] == "healthy"
    assert recovered["episode_started_at"] == 120.0


def test_bridge_preserves_recovery_history(
    tmp_path,
):
    clock = FakeClock()
    bridge = LCDReaderStatusBridge(
        tmp_path / "lcd-reader-status.json",
        clock=clock,
    )

    bridge.publish(
        {
            "connected": False,
            "thread_alive": True,
            "dispatcher_alive": True,
        }
    )

    clock.value = 110.0

    bridge.publish(
        {
            "connected": True,
            "thread_alive": True,
            "dispatcher_alive": True,
        }
    )

    clock.value = 120.0

    reader = bridge.publish(
        {
            "connected": True,
            "thread_alive": True,
            "dispatcher_alive": True,
        }
    )["reader"]

    assert reader["recovery_count"] == 1
    assert reader["last_recovery_at"] == 110.0
    assert reader["last_healthy_at"] == 120.0
    assert reader["episode_started_at"] == 110.0


def test_bridge_does_not_count_planned_restart_as_recovery(
    tmp_path,
):
    clock = FakeClock()
    bridge = LCDReaderStatusBridge(
        tmp_path / "lcd-reader-status.json",
        clock=clock,
    )

    bridge.publish(
        {
            "connected": True,
            "thread_alive": True,
            "dispatcher_alive": True,
            "stop_requested": False,
        }
    )

    clock.value = 110.0

    stopped = bridge.publish(
        {
            "connected": False,
            "thread_alive": False,
            "dispatcher_alive": False,
            "stop_requested": True,
        }
    )["reader"]

    assert stopped["healthy"] is False
    assert stopped["stop_requested"] is True
    assert stopped["recovery_count"] == 0

    clock.value = 120.0

    restarted = bridge.publish(
        {
            "connected": True,
            "thread_alive": True,
            "dispatcher_alive": True,
            "stop_requested": False,
        }
    )["reader"]

    assert restarted["healthy"] is True
    assert restarted["recovery_count"] == 0
    assert restarted["last_recovery_at"] is None
    assert restarted["episode_started_at"] == 120.0


def test_bridge_preserves_real_recovery_after_planned_restart(
    tmp_path,
):
    clock = FakeClock()
    bridge = LCDReaderStatusBridge(
        tmp_path / "lcd-reader-status.json",
        clock=clock,
    )

    bridge.publish(
        {
            "connected": False,
            "thread_alive": False,
            "dispatcher_alive": False,
            "stop_requested": False,
        }
    )

    clock.value = 110.0

    recovered = bridge.publish(
        {
            "connected": True,
            "thread_alive": True,
            "dispatcher_alive": True,
            "stop_requested": False,
        }
    )["reader"]

    assert recovered["recovery_count"] == 1
    assert recovered["last_recovery_at"] == 110.0

    clock.value = 120.0

    bridge.publish(
        {
            "connected": False,
            "thread_alive": False,
            "dispatcher_alive": False,
            "stop_requested": True,
        }
    )

    clock.value = 130.0

    restarted = bridge.publish(
        {
            "connected": True,
            "thread_alive": True,
            "dispatcher_alive": True,
            "stop_requested": False,
        }
    )["reader"]

    assert restarted["recovery_count"] == 1
    assert restarted["last_recovery_at"] == 110.0
