from types import SimpleNamespace

from truepanel.host.status import (
    publish_host_fan_status,
)


class FakeRuntime:
    def status_payload(self):
        return {
            "enabled": True,
            "connected": True,
            "active_profile": "automatic",
            "requested_profile": "automatic",
            "control_authority": "automatic",
            "safety_hold": False,
            "recovery_pending": False,
        }


class FakeLease:
    def active(self):
        return True

    def remaining_seconds(self):
        return 42.0


class FakeBridge:
    def __init__(self):
        self.payload = None

    def publish(self, payload):
        self.payload = dict(payload)
        return self.payload


def make_authority():
    return SimpleNamespace(
        policy_mode="automatic_control",
        operator_armed=True,
        coordinator=SimpleNamespace(
            dry_run=True,
            simulated_profile=SimpleNamespace(
                value="balanced",
            ),
        ),
        last_result=SimpleNamespace(
            state="dry_run",
            reason="Dry-run recommendation.",
            cooldown_remaining=3.0,
        ),
        supervised_session_deadline=150.0,
        automatic_lease=FakeLease(),
        current_fingerprint="current",
        commissioned_fingerprint="current",
        current_recommendation=SimpleNamespace(
            recommended_profile=SimpleNamespace(
                value="cooling_boost",
            ),
            hottest_temperature_c=51.0,
            reason="Temperature elevated.",
            changed=True,
            telemetry_valid=True,
        ),
    )


def test_status_publisher_uses_bridge_contract_keys():
    bridge = FakeBridge()

    payload = publish_host_fan_status(
        fan_runtime=FakeRuntime(),
        thermal_authority=make_authority(),
        status_bridge=bridge,
        monotonic=lambda: 100.0,
    )

    assert payload[
        "thermal_operator_armed"
    ] is True

    assert payload[
        "thermal_dry_run"
    ] is True

    assert (
        "thermal_authority.operator_armed"
        not in payload
    )

    assert (
        "thermal_authority.dry_run"
        not in payload
    )


def test_status_publisher_normalizes_host_state():
    bridge = FakeBridge()

    payload = publish_host_fan_status(
        fan_runtime=FakeRuntime(),
        thermal_authority=make_authority(),
        status_bridge=bridge,
        reason="Host status test.",
        monotonic=lambda: 100.0,
    )

    assert payload["last_reason"] == (
        "Host status test."
    )

    assert payload[
        "thermal_policy_mode"
    ] == "automatic_control"

    assert payload[
        "thermal_control_state"
    ] == "dry_run"

    assert payload[
        "thermal_simulated_profile"
    ] == "balanced"

    assert payload[
        "thermal_supervised_session_active"
    ] is True

    assert payload[
        "thermal_supervised_session_remaining"
    ] == 50.0

    assert payload[
        "thermal_automatic_lease_active"
    ] is True

    assert payload[
        "thermal_automatic_lease_remaining"
    ] == 42.0

    assert payload[
        "thermal_commissioned_fingerprint_match"
    ] is True

    assert payload[
        "thermal_recommended_profile"
    ] == "cooling_boost"

    assert payload[
        "thermal_hottest_temperature_c"
    ] == 51.0

    assert payload[
        "thermal_telemetry_valid"
    ] is True


def test_status_publisher_handles_missing_recommendation():
    authority = make_authority()
    authority.current_recommendation = None

    payload = publish_host_fan_status(
        fan_runtime=FakeRuntime(),
        thermal_authority=authority,
        status_bridge=FakeBridge(),
        monotonic=lambda: 100.0,
    )

    assert payload[
        "thermal_recommended_profile"
    ] == "automatic"

    assert payload[
        "thermal_hottest_temperature_c"
    ] is None

    assert payload[
        "thermal_recommendation_changed"
    ] is False

    assert payload[
        "thermal_telemetry_valid"
    ] is False
