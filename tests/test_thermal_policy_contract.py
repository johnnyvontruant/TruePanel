from pathlib import Path

from truepanel.hardware.fan_control import (
    FanProfile,
)
from truepanel.hardware.fan_status_bridge import (
    FanControlStatusBridge,
    normalize_thermal_policy_mode,
    thermal_profile_alignment,
)
from truepanel.hardware.thermal_fan_policy import (
    ThermalFanPolicy,
)


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += float(seconds)


def test_policy_modes_normalize_safely():
    assert normalize_thermal_policy_mode(
        "disabled"
    ) == "disabled"

    assert normalize_thermal_policy_mode(
        "observe_only"
    ) == "observe_only"

    assert normalize_thermal_policy_mode(
        "automatic_control"
    ) == "automatic_control"

    assert normalize_thermal_policy_mode(
        "warp_drive"
    ) == "observe_only"


def test_profile_alignment_states():
    assert thermal_profile_alignment(
        recommended_profile="balanced",
        active_profile="balanced",
        telemetry_valid=True,
    ) == "aligned"

    assert thermal_profile_alignment(
        recommended_profile="cooling_boost",
        active_profile="automatic",
        telemetry_valid=True,
    ) == "action_recommended"

    assert thermal_profile_alignment(
        recommended_profile="afterburners",
        active_profile="automatic",
        telemetry_valid=False,
    ) == "telemetry_unavailable"


def test_bridge_preserves_unarmed_automatic_control(
    tmp_path,
):
    bridge = FanControlStatusBridge(
        tmp_path / "status.json",
        clock=lambda: 100.0,
    )

    bridge.publish(
        {
            "enabled": True,
            "connected": True,
            "active_profile": "automatic",
            "thermal_policy_mode": "automatic_control",
            "thermal_recommended_profile": "balanced",
            "thermal_telemetry_valid": True,
        }
    )

    payload = bridge.read(
        max_age=30
    )

    assert payload is not None
    assert (
        payload["thermal_policy_mode"]
        == "automatic_control"
    )
    assert (
        payload["thermal_profile_alignment"]
        == "action_recommended"
    )
    assert payload["active_profile"] == "automatic"


def test_complete_thermal_ascent_and_recovery():
    clock = FakeClock()

    policy = ThermalFanPolicy(
        balanced_temperature_c=42,
        cooling_boost_temperature_c=50,
        afterburners_temperature_c=60,
        hysteresis_c=3,
        minimum_dwell_seconds=30,
        clock=clock,
    )

    assert policy.evaluate(
        (35,)
    ).recommended_profile is FanProfile.QUIET

    clock.advance(1)

    assert policy.evaluate(
        (43,)
    ).recommended_profile is FanProfile.BALANCED

    clock.advance(1)

    assert policy.evaluate(
        (51,)
    ).recommended_profile is FanProfile.COOLING_BOOST

    clock.advance(1)

    assert policy.evaluate(
        (61,)
    ).recommended_profile is FanProfile.AFTERBURNERS

    clock.advance(10)

    held = policy.evaluate(
        (55,)
    )

    assert (
        held.recommended_profile
        is FanProfile.AFTERBURNERS
    )
    assert "minimum dwell" in held.reason

    clock.advance(20)

    assert policy.evaluate(
        (55,)
    ).recommended_profile is FanProfile.COOLING_BOOST

    clock.advance(30)

    assert policy.evaluate(
        (46,)
    ).recommended_profile is FanProfile.BALANCED

    clock.advance(30)

    assert policy.evaluate(
        (38,)
    ).recommended_profile is FanProfile.QUIET


def test_sensor_loss_recommends_automatic():
    policy = ThermalFanPolicy(
        initial_profile=FanProfile.AFTERBURNERS
    )

    result = policy.evaluate(
        (),
        telemetry_fresh=False,
    )

    assert (
        result.recommended_profile
        is FanProfile.AUTOMATIC
    )
    assert result.telemetry_valid is False


def test_observer_has_no_actuator_path():
    source = Path(
        "lcd-menu.py"
    ).read_text(
        encoding="utf-8"
    )

    start = source.index(
        "def observe_thermal_fan_policy("
    )
    end = source.index(
        "def record_fan_control_event(",
        start,
    )

    observer = source[start:end]

    for forbidden in (
        "request_profile(",
        "fan_command_client",
        "set_manual_pwm",
        "FanHardwareExecutor",
        "fan_control_runtime.request",
    ):
        assert forbidden not in observer

    assert (
        "automatic_control mode is intentionally unarmed"
        in observer
    )


def test_default_mode_remains_observe_only():
    source = Path(
        "truepanel/config/loader.py"
    ).read_text(
        encoding="utf-8"
    )

    assert '"mode": "observe_only"' in source


def test_dashboard_exposes_alignment():
    source = Path(
        "truepanel/web/static/index.html"
    ).read_text(
        encoding="utf-8"
    )

    assert 'id="fanThermalAlignment"' in source
    assert "Aligned with active profile" in source
    assert "Action recommended:" in source
    assert "Automatic control · Unarmed" in source
