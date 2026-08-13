from pathlib import Path

from truepanel.hardware.fan_status_bridge import (
    FanControlStatusBridge,
)
from truepanel.host.client import HostAgentStatusClient


def test_status_client_reads_fresh_published_snapshot(tmp_path):
    status_path = tmp_path / "fan-control-status.json"
    bridge = FanControlStatusBridge(
        status_path,
        clock=lambda: 100.0,
    )
    bridge.publish(
        {
            "enabled": True,
            "connected": True,
            "active_profile": "balanced",
        }
    )

    client = HostAgentStatusClient(
        path=status_path,
        reader=FanControlStatusBridge(
            status_path,
            clock=lambda: 105.0,
        ).read,
    )

    status = client.read_fan_status(
        max_age=30.0
    )

    assert status is not None
    assert status["connected"] is True
    assert status["active_profile"] == "balanced"
    assert status["age_seconds"] == 5.0


def test_status_client_rejects_stale_snapshot(tmp_path):
    status_path = tmp_path / "fan-control-status.json"
    bridge = FanControlStatusBridge(
        status_path,
        clock=lambda: 100.0,
    )
    bridge.publish(
        {
            "enabled": True,
            "connected": True,
        }
    )

    client = HostAgentStatusClient(
        path=status_path,
        reader=FanControlStatusBridge(
            status_path,
            clock=lambda: 140.0,
        ).read,
    )

    assert (
        client.read_fan_status(
            max_age=30.0
        )
        is None
    )


def test_status_client_forwards_max_age_to_reader():
    calls = []

    def reader(*, max_age):
        calls.append(max_age)
        return {"connected": False}

    client = HostAgentStatusClient(
        reader=reader
    )

    assert client.read_fan_status(
        max_age=12.5
    ) == {"connected": False}
    assert calls == [12.5]


def test_status_client_has_no_command_or_hardware_surface():
    source = Path(
        "truepanel/host/client.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "FanCommand",
        "HostOwnership",
        "fan-control.sock",
        "fcntl",
        "flock",
        "subprocess",
        ".publish(",
        ".write_text(",
        ".mkdir(",
        ".unlink(",
        "request_profile(",
        "set_manual_pwm",
    ):
        assert forbidden not in source
