import pytest

from truepanel.hardware.fan_control import (
    FanControlDecision,
    FanProfile,
)
from truepanel.hardware.thermal_control import (
    ThermalControlCoordinator,
)


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += float(seconds)


class Recommendation:
    def __init__(
        self,
        profile,
        *,
        telemetry_valid=True,
    ):
        self.recommended_profile = profile
        self.telemetry_valid = telemetry_valid


class FakeService:
    def __init__(self):
        self.requests = []

    def request_profile(
        self,
        profile,
        *,
        fan_status,
        temperatures_c,
        telemetry_fresh,
    ):
        profile = FanProfile(profile)

        self.requests.append(
            {
                "profile": profile,
                "fan_status": fan_status,
                "temperatures_c": (
                    temperatures_c
                ),
                "telemetry_fresh": (
                    telemetry_fresh
                ),
            }
        )

        return FanControlDecision(
            accepted=True,
            requested_profile=profile,
            effective_profile=profile,
            pwm=(
                None
                if profile
                is FanProfile.AUTOMATIC
                else 194
            ),
            reason="Applied by fake service.",
            force_automatic=(
                profile
                is FanProfile.AUTOMATIC
            ),
        )


def telemetry(
    *,
    fresh=True,
):
    return {
        "fan_status": {
            "fan_channels": [
                {
                    "number": 1,
                    "rpm": 1500,
                    "alarm": False,
                },
                {
                    "number": 2,
                    "rpm": 1500,
                    "alarm": False,
                },
            ]
        },
        "temperatures_c": (
            47.0,
            39.0,
        ),
        "telemetry_fresh": fresh,
    }


def runtime_status(
    *,
    active="automatic",
    connected=True,
    safety_hold=False,
    recovery_pending=False,
):
    return {
        "active_profile": active,
        "connected": connected,
        "safety_hold": safety_hold,
        "recovery_pending": (
            recovery_pending
        ),
    }


def coordinator(
    service,
    *,
    clock=None,
    mode="automatic_control",
    armed=True,
    cooldown=30,
):
    return ThermalControlCoordinator(
        service,
        policy_mode=mode,
        operator_armed=armed,
        command_cooldown_seconds=(
            cooldown
        ),
        clock=clock,
    )


def test_default_coordinator_is_unarmed():
    service = FakeService()
    control = ThermalControlCoordinator(
        service
    )

    result = control.evaluate(
        Recommendation(
            FanProfile.BALANCED
        ),
        telemetry=telemetry(),
        runtime_status=runtime_status(),
    )

    assert result.state == "blocked"
    assert result.owns_control is False
    assert service.requests == []


def test_observe_only_never_requests_profile():
    service = FakeService()
    control = coordinator(
        service,
        mode="observe_only",
    )

    result = control.evaluate(
        Recommendation(
            FanProfile.COOLING_BOOST
        ),
        telemetry=telemetry(),
        runtime_status=runtime_status(),
    )

    assert result.state == "blocked"
    assert service.requests == []


def test_unarmed_automatic_mode_never_requests_profile():
    service = FakeService()
    control = coordinator(
        service,
        armed=False,
    )

    result = control.evaluate(
        Recommendation(
            FanProfile.BALANCED
        ),
        telemetry=telemetry(),
        runtime_status=runtime_status(),
    )

    assert result.state == "blocked"
    assert service.requests == []


def test_armed_control_applies_recommendation():
    service = FakeService()
    control = coordinator(
        service
    )

    result = control.evaluate(
        Recommendation(
            FanProfile.BALANCED
        ),
        telemetry=telemetry(),
        runtime_status=runtime_status(),
    )

    assert result.state == "applied"
    assert result.owns_control is True
    assert (
        service.requests[-1]["profile"]
        is FanProfile.BALANCED
    )


def test_request_uses_current_telemetry():
    service = FakeService()
    control = coordinator(
        service
    )
    current = telemetry()

    control.evaluate(
        Recommendation(
            FanProfile.BALANCED
        ),
        telemetry=current,
        runtime_status=runtime_status(),
    )

    request = service.requests[-1]

    assert (
        request["fan_status"]
        is current["fan_status"]
    )
    assert (
        request["temperatures_c"]
        == current["temperatures_c"]
    )
    assert request["telemetry_fresh"] is True


def test_aligned_profile_does_not_repeat_request():
    service = FakeService()
    control = coordinator(
        service
    )

    result = control.evaluate(
        Recommendation(
            FanProfile.BALANCED
        ),
        telemetry=telemetry(),
        runtime_status=runtime_status(
            active="balanced"
        ),
    )

    assert result.state == "aligned"
    assert result.owns_control is True
    assert service.requests == []


def test_upshift_bypasses_command_cooldown():
    service = FakeService()
    clock = FakeClock()
    control = coordinator(
        service,
        clock=clock,
        cooldown=300,
    )

    control.evaluate(
        Recommendation(
            FanProfile.BALANCED
        ),
        telemetry=telemetry(),
        runtime_status=runtime_status(),
    )

    clock.advance(1)

    result = control.evaluate(
        Recommendation(
            FanProfile.COOLING_BOOST
        ),
        telemetry=telemetry(),
        runtime_status=runtime_status(
            active="balanced"
        ),
    )

    assert result.state == "applied"
    assert (
        service.requests[-1]["profile"]
        is FanProfile.COOLING_BOOST
    )


def test_afterburners_upshift_is_immediate():
    service = FakeService()
    clock = FakeClock()
    control = coordinator(
        service,
        clock=clock,
        cooldown=300,
    )

    control.evaluate(
        Recommendation(
            FanProfile.BALANCED
        ),
        telemetry=telemetry(),
        runtime_status=runtime_status(),
    )

    clock.advance(1)

    result = control.evaluate(
        Recommendation(
            FanProfile.AFTERBURNERS
        ),
        telemetry=telemetry(),
        runtime_status=runtime_status(
            active="balanced"
        ),
    )

    assert result.state == "applied"
    assert (
        service.requests[-1]["profile"]
        is FanProfile.AFTERBURNERS
    )


def test_downshift_waits_for_command_cooldown():
    service = FakeService()
    clock = FakeClock()
    control = coordinator(
        service,
        clock=clock,
        cooldown=30,
    )

    control.evaluate(
        Recommendation(
            FanProfile.COOLING_BOOST
        ),
        telemetry=telemetry(),
        runtime_status=runtime_status(),
    )

    clock.advance(10)

    result = control.evaluate(
        Recommendation(
            FanProfile.BALANCED
        ),
        telemetry=telemetry(),
        runtime_status=runtime_status(
            active="cooling_boost"
        ),
    )

    assert result.state == "cooldown"
    assert result.cooldown_remaining == 20
    assert len(service.requests) == 1


def test_downshift_applies_after_cooldown():
    service = FakeService()
    clock = FakeClock()
    control = coordinator(
        service,
        clock=clock,
        cooldown=30,
    )

    control.evaluate(
        Recommendation(
            FanProfile.COOLING_BOOST
        ),
        telemetry=telemetry(),
        runtime_status=runtime_status(),
    )

    clock.advance(30)

    result = control.evaluate(
        Recommendation(
            FanProfile.BALANCED
        ),
        telemetry=telemetry(),
        runtime_status=runtime_status(
            active="cooling_boost"
        ),
    )

    assert result.state == "applied"
    assert (
        service.requests[-1]["profile"]
        is FanProfile.BALANCED
    )


def test_stale_recommendation_releases_owned_control():
    service = FakeService()
    control = coordinator(
        service
    )

    control.owns_control = True

    result = control.evaluate(
        Recommendation(
            FanProfile.AUTOMATIC,
            telemetry_valid=False,
        ),
        telemetry=telemetry(
            fresh=False
        ),
        runtime_status=runtime_status(
            active="balanced"
        ),
    )

    assert result.state == "released"
    assert result.owns_control is False
    assert (
        service.requests[-1]["profile"]
        is FanProfile.AUTOMATIC
    )


def test_disarming_releases_owned_control():
    service = FakeService()
    control = coordinator(
        service
    )
    control.owns_control = True
    control.configure(
        operator_armed=False
    )

    result = control.evaluate(
        Recommendation(
            FanProfile.BALANCED
        ),
        telemetry=telemetry(),
        runtime_status=runtime_status(
            active="balanced"
        ),
    )

    assert result.state == "released"
    assert (
        service.requests[-1]["profile"]
        is FanProfile.AUTOMATIC
    )


def test_safety_hold_blocks_without_actuation():
    service = FakeService()
    control = coordinator(
        service
    )

    result = control.evaluate(
        Recommendation(
            FanProfile.COOLING_BOOST
        ),
        telemetry=telemetry(),
        runtime_status=runtime_status(
            active="afterburners",
            safety_hold=True,
        ),
    )

    assert result.state == "blocked"
    assert service.requests == []


def test_recovery_pending_blocks_without_actuation():
    service = FakeService()
    control = coordinator(
        service
    )

    result = control.evaluate(
        Recommendation(
            FanProfile.COOLING_BOOST
        ),
        telemetry=telemetry(),
        runtime_status=runtime_status(
            active="afterburners",
            recovery_pending=True,
        ),
    )

    assert result.state == "blocked"
    assert service.requests == []


def test_disconnected_runtime_blocks():
    service = FakeService()
    control = coordinator(
        service
    )

    result = control.evaluate(
        Recommendation(
            FanProfile.BALANCED
        ),
        telemetry=telemetry(),
        runtime_status=runtime_status(
            connected=False
        ),
    )

    assert result.state == "blocked"
    assert service.requests == []


def test_negative_cooldown_is_rejected():
    with pytest.raises(
        ValueError,
        match="cannot be negative",
    ):
        ThermalControlCoordinator(
            FakeService(),
            command_cooldown_seconds=-1,
        )


def test_module_contains_no_hardware_write_path():
    from pathlib import Path

    source = Path(
        "truepanel/hardware/"
        "thermal_control.py"
    ).read_text(
        encoding="utf-8"
    )

    for forbidden in (
        "/sys/",
        "write_int",
        "set_manual_pwm",
        "FanHardwareExecutor",
    ):
        assert forbidden not in source


def test_production_defaults_remain_locked():
    from pathlib import Path

    source = Path(
        "truepanel/config/loader.py"
    ).read_text(
        encoding="utf-8"
    )

    assert '"mode": "observe_only"' in source
    assert '"operator_armed": False' in source


def test_status_bridge_uses_published_arm_state():
    from pathlib import Path

    source = Path(
        "truepanel/hardware/"
        "fan_status_bridge.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        '"thermal_operator_armed"'
        in source
    )
    assert "operator_armed=False" not in source


def test_lcd_constructs_thermal_coordinator():
    from pathlib import Path

    source = Path(
        "lcd-menu.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "ThermalControlCoordinator"
        in source
    )
    assert (
        "thermal_control_coordinator = ("
        in source
    )
    assert (
        '"operator_armed",'
        in source
    )
    assert (
        '"command_cooldown_seconds",'
        in source
    )


def test_safety_reconcile_precedes_thermal_control():
    from pathlib import Path

    source = Path(
        "lcd-menu.py"
    ).read_text(
        encoding="utf-8"
    )

    start = source.index(
        "def reconcile_fan_control():"
    )
    end = source.index(
        "def build_fan_command_server():",
        start,
    )
    reconcile = source[start:end]

    safety_tick = reconcile.index(
        "fan_control_runtime.service.tick("
    )
    thermal_evaluate = reconcile.index(
        "thermal_control_coordinator.evaluate("
    )

    assert safety_tick < thermal_evaluate


def test_thermal_transition_uses_existing_history():
    from pathlib import Path

    source = Path(
        "lcd-menu.py"
    ).read_text(
        encoding="utf-8"
    )

    start = source.index(
        "def reconcile_fan_control():"
    )
    end = source.index(
        "def build_fan_command_server():",
        start,
    )
    reconcile = source[start:end]

    assert (
        'source="thermal_policy"'
        in reconcile
    )
    assert (
        "record_fan_control_event("
        in reconcile
    )
