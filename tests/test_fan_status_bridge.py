import json

from truepanel.hardware.fan_status_bridge import (
    FanControlStatusBridge,
)


class FakeClock:
    def __init__(
        self,
        value=100.0,
    ):
        self.value = float(
            value
        )

    def __call__(self):
        return self.value


def test_bridge_publishes_and_reads_status(
    tmp_path,
):
    clock = FakeClock()
    path = (
        tmp_path
        / "fan-control-status.json"
    )

    bridge = FanControlStatusBridge(
        path,
        clock=clock,
    )

    bridge.publish(
        {
            "enabled": False,
            "connected": False,
            "active_profile": (
                "automatic"
            ),
            "requested_profile": (
                "automatic"
            ),
            "remaining_seconds": None,
            "last_reason": (
                "Fan control is disabled."
            ),
        }
    )

    payload = bridge.read()

    assert payload is not None
    assert payload["timestamp"] == 100.0
    assert payload["age_seconds"] == 0.0
    assert payload["enabled"] is False
    assert payload["connected"] is False
    assert (
        payload["active_profile"]
        == "automatic"
    )


def test_bridge_replaces_file_atomically(
    tmp_path,
):
    clock = FakeClock()
    path = (
        tmp_path
        / "fan-control-status.json"
    )

    bridge = FanControlStatusBridge(
        path,
        clock=clock,
    )

    bridge.publish(
        {
            "last_reason": "first",
        }
    )

    first_inode = path.stat().st_ino

    clock.value = 101.0

    bridge.publish(
        {
            "last_reason": "second",
        }
    )

    second_inode = path.stat().st_ino

    assert first_inode != second_inode
    assert json.loads(
        path.read_text()
    )["last_reason"] == "second"


def test_bridge_rejects_stale_status(
    tmp_path,
):
    clock = FakeClock()
    path = (
        tmp_path
        / "fan-control-status.json"
    )

    bridge = FanControlStatusBridge(
        path,
        clock=clock,
    )

    bridge.publish(
        {
            "connected": True,
        }
    )

    clock.value += 31

    assert (
        bridge.read(
            max_age=30
        )
        is None
    )


def test_bridge_rejects_invalid_json(
    tmp_path,
):
    path = (
        tmp_path
        / "fan-control-status.json"
    )
    path.write_text(
        "not-json"
    )

    bridge = FanControlStatusBridge(
        path
    )

    assert bridge.read() is None


def test_bridge_normalizes_unknown_profiles(
    tmp_path,
):
    bridge = FanControlStatusBridge(
        tmp_path
        / "fan-control-status.json"
    )

    published = bridge.publish(
        {
            "active_profile": (
                "warp-eleven"
            ),
            "requested_profile": (
                "ludicrous"
            ),
        }
    )

    assert (
        published["active_profile"]
        == "automatic"
    )
    assert (
        published["requested_profile"]
        == "automatic"
    )


def test_bridge_preserves_fan_safety_state(
    tmp_path,
):
    bridge = FanControlStatusBridge(
        tmp_path / "fan-status.json",
        clock=lambda: 100.0,
    )

    bridge.publish(
        {
            "enabled": True,
            "connected": True,
            "active_profile": "afterburners",
            "requested_profile": "afterburners",
            "remaining_seconds": None,
            "last_reason": "Recovery underway.",
            "control_authority": "safety",
            "safety_hold": True,
            "recovery_pending": True,
            "recovery_healthy_cycles": 2,
            "recovery_required_cycles": 3,
        }
    )

    payload = bridge.read(
        max_age=30.0
    )

    assert payload is not None
    assert payload["control_authority"] == "safety"
    assert payload["safety_hold"] is True
    assert payload["recovery_pending"] is True
    assert payload["recovery_healthy_cycles"] == 2
    assert payload["recovery_required_cycles"] == 3


def test_bridge_preserves_observe_only_thermal_status(
    tmp_path,
):
    bridge = FanControlStatusBridge(
        tmp_path / "fan-status.json",
        clock=lambda: 100.0,
    )

    bridge.publish(
        {
            "enabled": True,
            "connected": True,
            "thermal_policy_mode": "observe_only",
            "thermal_recommended_profile": "balanced",
            "thermal_hottest_temperature_c": 47.0,
            "thermal_recommendation_reason": (
                "Thermal recommendation remains balanced."
            ),
            "thermal_recommendation_changed": False,
            "thermal_telemetry_valid": True,
        }
    )

    payload = bridge.read(
        max_age=30.0
    )

    assert payload is not None
    assert (
        payload["thermal_policy_mode"]
        == "observe_only"
    )
    assert (
        payload["thermal_recommended_profile"]
        == "balanced"
    )
    assert (
        payload["thermal_hottest_temperature_c"]
        == 47.0
    )
    assert payload["thermal_telemetry_valid"] is True


def test_bridge_publishes_armed_thermal_readiness(
    tmp_path,
):
    bridge = FanControlStatusBridge(
        tmp_path / "fan-status.json",
        clock=lambda: 100.0,
    )

    bridge.publish(
        {
            "enabled": True,
            "connected": True,
            "active_profile": "automatic",
            "thermal_policy_mode": (
                "automatic_control"
            ),
            "thermal_operator_armed": True,
            "thermal_recommended_profile": (
                "balanced"
            ),
            "thermal_telemetry_valid": True,
            "safety_hold": False,
            "recovery_pending": False,
        }
    )

    payload = bridge.read(
        max_age=30.0
    )

    readiness = payload[
        "thermal_control_readiness"
    ]

    assert readiness["ready"] is True
    assert readiness["armed"] is True
    assert readiness["state"] == "armed"
    assert (
        readiness["checks"][
            "operator_armed"
        ]
        is True
    )
