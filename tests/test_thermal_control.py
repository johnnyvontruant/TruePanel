from pathlib import Path

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
    dry_run=False,
    cooldown=30,
):
    return ThermalControlCoordinator(
        service,
        policy_mode=mode,
        operator_armed=armed,
        dry_run=dry_run,
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

    runtime = Path(
        "lcd-menu.py"
    ).read_text(
        encoding="utf-8"
    )

    bootstrap = Path(
        "truepanel/host/bootstrap.py"
    ).read_text(
        encoding="utf-8"
    )

    authority = Path(
        "truepanel/host/thermal_authority.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "build_host_agent_bootstrap("
        in runtime
    )

    assert (
        "thermal_authority_factory="
        "HostThermalAuthority"
        in bootstrap
    )

    assert (
        "thermal_authority = "
        "thermal_authority_factory("
        in bootstrap
    )

    assert (
        "ThermalControlCoordinator("
        in authority
    )

def test_safety_reconcile_precedes_thermal_control():
    reconciliation = Path(
        "truepanel/host/reconciliation.py"
    ).read_text()
    safety = Path("truepanel/host/safety.py").read_text()

    assert "service.tick(" in safety
    assert reconciliation.index("self._safety.reconcile(") < reconciliation.index(
        "self._thermal_authority.reconcile("
    )

def test_thermal_transition_uses_existing_history():
    reconciliation = Path(
        "truepanel/host/reconciliation.py"
    ).read_text()

    assert "record_fan_event=self._record_fan_event" in reconciliation
    assert "record_commissioning_event=(" in reconciliation

def test_dry_run_simulates_without_service_request():
    service = FakeService()

    control = ThermalControlCoordinator(
        service,
        policy_mode="automatic_control",
        operator_armed=True,
        dry_run=True,
        command_cooldown_seconds=30,
    )

    result = control.evaluate(
        Recommendation(
            FanProfile.BALANCED
        ),
        telemetry=telemetry(),
        runtime_status=runtime_status(),
    )

    assert result.state == "simulated"
    assert result.decision is None
    assert result.owns_control is False
    assert (
        result.requested_profile
        is FanProfile.BALANCED
    )
    assert (
        control.simulated_profile
        is FanProfile.BALANCED
    )
    assert service.requests == []


def test_dry_run_does_not_repeat_simulated_profile():
    service = FakeService()

    control = ThermalControlCoordinator(
        service,
        policy_mode="automatic_control",
        operator_armed=True,
        dry_run=True,
    )

    control.evaluate(
        Recommendation(
            FanProfile.BALANCED
        ),
        telemetry=telemetry(),
        runtime_status=runtime_status(),
    )

    result = control.evaluate(
        Recommendation(
            FanProfile.BALANCED
        ),
        telemetry=telemetry(),
        runtime_status=runtime_status(),
    )

    assert result.state == "aligned"
    assert service.requests == []


def test_dry_run_upshift_bypasses_cooldown():
    service = FakeService()
    clock = FakeClock()

    control = ThermalControlCoordinator(
        service,
        policy_mode="automatic_control",
        operator_armed=True,
        dry_run=True,
        command_cooldown_seconds=300,
        clock=clock,
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
        runtime_status=runtime_status(),
    )

    assert result.state == "simulated"
    assert (
        control.simulated_profile
        is FanProfile.COOLING_BOOST
    )
    assert service.requests == []


def test_dry_run_downshift_obeys_cooldown():
    service = FakeService()
    clock = FakeClock()

    control = ThermalControlCoordinator(
        service,
        policy_mode="automatic_control",
        operator_armed=True,
        dry_run=True,
        command_cooldown_seconds=30,
        clock=clock,
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
        runtime_status=runtime_status(),
    )

    assert result.state == "cooldown"
    assert result.cooldown_remaining == 20
    assert (
        control.simulated_profile
        is FanProfile.COOLING_BOOST
    )
    assert service.requests == []


def test_dry_run_returns_simulation_to_automatic():
    service = FakeService()

    control = ThermalControlCoordinator(
        service,
        policy_mode="automatic_control",
        operator_armed=True,
        dry_run=True,
    )

    control.evaluate(
        Recommendation(
            FanProfile.BALANCED
        ),
        telemetry=telemetry(),
        runtime_status=runtime_status(),
    )

    result = control.evaluate(
        Recommendation(
            FanProfile.AUTOMATIC,
            telemetry_valid=False,
        ),
        telemetry=telemetry(
            fresh=False
        ),
        runtime_status=runtime_status(),
    )

    assert result.state == "simulated"
    assert (
        control.simulated_profile
        is FanProfile.AUTOMATIC
    )
    assert service.requests == []


def test_source_default_enables_dry_run_lock():
    from pathlib import Path

    source = Path(
        "truepanel/config/loader.py"
    ).read_text(
        encoding="utf-8"
    )

    assert '"dry_run": True' in source



def test_supervised_live_session_is_time_limited_and_balanced_only():
    authority = Path(
        "truepanel/host/thermal_authority.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "self.supervised_session_seconds"
        in authority
    )

    start = authority.index(
        'elif normalized == "supervised_live":'
    )

    end = authority.index(
        'elif normalized == "arm":',
        start,
    )

    supervised = authority[start:end]

    assert '"balanced"' in supervised

    assert (
        "self.supervised_session_seconds"
        in supervised
    )

def test_supervised_live_session_requires_automatic_start():
    authority = Path(
        "truepanel/host/thermal_authority.py"
    ).read_text(
        encoding="utf-8"
    )

    start = authority.index(
        'elif normalized == "supervised_live":'
    )

    end = authority.index(
        'elif normalized == "arm":',
        start,
    )

    supervised = authority[start:end]

    assert (
        'runtime_status.get('
        in supervised
    )

    assert '!= "automatic"' in supervised

    assert (
        "Supervised live control must begin "
        in supervised
    )

def test_supervised_session_expiry_restores_dry_run():
    authority = Path(
        "truepanel/host/thermal_authority.py"
    ).read_text(
        encoding="utf-8"
    )

    start = authority.index(
        "def end_supervised_session("
    )

    end = authority.index(
        "def end_automatic_lease(",
        start,
    )

    helper = authority[start:end]

    assert (
        "self.operator_armed = False"
        in helper
    )

    assert (
        "operator_armed=False"
        in helper
    )

    assert "dry_run=True" in helper

    assert (
        "self.last_result = None"
        in helper
    )

def test_fan_safety_tick_precedes_supervised_lease_checks():
    reconciliation = Path(
        "truepanel/host/reconciliation.py"
    ).read_text()
    safety = Path("truepanel/host/safety.py").read_text()

    assert "service.tick(" in safety
    assert reconciliation.index("self._safety.reconcile(") < reconciliation.index(
        "self._thermal_authority.reconcile("
    )

def test_safety_decision_disarms_lease_without_requesting_automatic():
    reconciliation = Path(
        "truepanel/host/reconciliation.py"
    ).read_text()

    assert "if decision is not None:" in reconciliation
    assert reconciliation.index("if decision is not None:") < reconciliation.index(
        "self._thermal_authority.reconcile("
    )
    assert "handle_fan_safety_transition" in reconciliation

def test_supervised_live_response_is_not_labeled_dry_run():
    authority = Path(
        "truepanel/host/thermal_authority.py"
    ).read_text(
        encoding="utf-8"
    )

    assert '"supervised_live"' in authority

    assert (
        '"status": ('
        in authority
    )

    assert (
        '"supervised_live"'
        in authority[
            authority.index(
                "return {",
                authority.index(
                    'elif normalized == "supervised_live":'
                ),
            ):
        ]
    )

def test_supervised_handler_declares_deadline_global():
    from pathlib import Path

    source = Path(
        "lcd-menu.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "global supervised_thermal_session_deadline"
        not in source
    )

    status = Path(
        "truepanel/host/status.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "thermal_authority" in status
    assert ".supervised_session_deadline" in status

def test_supervised_handler_sets_bounded_deadline():
    authority = Path(
        "truepanel/host/thermal_authority.py"
    ).read_text(
        encoding="utf-8"
    )

    start = authority.index(
        'elif normalized == "supervised_live":'
    )

    end = authority.index(
        'elif normalized == "arm":',
        start,
    )

    handler = authority[start:end]

    assert (
        "self.supervised_session_deadline"
        in handler
    )

    assert "self.clock()" in handler

    assert (
        "+ self.supervised_session_seconds"
        in handler
    )

def test_disarm_synchronously_restores_motherboard_control():
    authority = Path(
        "truepanel/host/thermal_authority.py"
    ).read_text(
        encoding="utf-8"
    )

    start = authority.index(
        "else:\n"
        "            was_supervised = ("
    )

    end = authority.index(
        "\n        if (",
        start,
    )

    disarm = authority[start:end]

    restore_position = disarm.index(
        "restore_automatic("
    )

    safe_state_position = disarm.index(
        "self.coordinator.configure("
    )

    assert (
        restore_position
        < safe_state_position
    )

    assert (
        "self.operator_armed = False"
        in disarm
    )

def test_lease_expiry_uses_synchronous_restoration():
    authority = Path(
        "truepanel/host/thermal_authority.py"
    ).read_text(
        encoding="utf-8"
    )

    start = authority.index(
        "def end_supervised_session("
    )

    end = authority.index(
        "def end_automatic_lease(",
        start,
    )

    helper = authority[start:end]

    restore = helper.index(
        "restore_automatic("
    )

    reset = helper.index(
        "self.coordinator.configure("
    )

    assert restore < reset

def test_disarm_message_reports_motherboard_restoration():
    authority = Path(
        "truepanel/host/thermal_authority.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "Automatic thermal control disarmed; "
        in authority
    )

    assert (
        "motherboard control restored."
        in authority
    )

def test_thermal_runtime_always_starts_disarmed():
    from pathlib import Path

    source = Path(
        "truepanel/host/thermal_authority.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "self.operator_armed = False" in source

    assert (
        "operator_armed=False"
        in source
    )

def test_thermal_runtime_always_starts_in_dry_run():
    from pathlib import Path

    source = Path(
        "truepanel/host/thermal_authority.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "self.dry_run = True" in source
    assert "dry_run=True" in source

def test_configuration_cannot_grant_startup_authority():
    from pathlib import Path

    source = Path(
        "truepanel/host/thermal_authority.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "operator_armed=False"
        in source
    )

    assert "dry_run=True" in source

    assert (
        "operator_armed:"
        not in source[
            source.index(
                "def __init__("
            ):
            source.index(
                "self.operator_armed = False"
            )
        ]
    )

def test_guarded_runtime_commands_can_still_arm():
    runtime = Path(
        "lcd-menu.py"
    ).read_text(
        encoding="utf-8"
    )

    authority = Path(
        "truepanel/host/thermal_authority.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "thermal_authority.handle_action("
        in runtime
    )

    assert (
        "self.operator_armed = True"
        in authority
    )

    assert (
        "self.coordinator.configure("
        in authority
    )


def test_lcd_records_supervised_commissioning_lifecycle():
    from pathlib import Path

    runtime = Path(
        "lcd-menu.py"
    ).read_text(
        encoding="utf-8"
    )

    bootstrap = Path(
        "truepanel/host/bootstrap.py"
    ).read_text(
        encoding="utf-8"
    )

    authority = Path(
        "truepanel/host/thermal_authority.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "host_bootstrap."
        "thermal_commissioning_history"
        in runtime
    )

    assert (
        "ThermalCommissioningHistory"
        in bootstrap
    )

    assert (
        "record_commissioning_event"
        in authority
    )

def test_session_end_requires_lifecycle_action():
    authority = Path(
        "truepanel/host/thermal_authority.py"
    ).read_text(
        encoding="utf-8"
    )

    start = authority.index(
        "def end_supervised_session("
    )

    end = authority.index(
        "def end_automatic_lease(",
        start,
    )

    helper = authority[start:end]

    assert "lifecycle_action" in helper

    assert (
        "record_commissioning_event("
        in helper
    )

def test_commissioning_history_has_no_hardware_path():
    source = Path(
        "truepanel/history/"
        "thermal_commissioning.py"
    ).read_text(
        encoding="utf-8"
    )

    for forbidden in (
        "request_profile",
        "service.tick",
        "FanHardwareExecutor",
        "set_manual_pwm",
        "write_int",
        "/sys/",
    ):
        assert forbidden not in source
