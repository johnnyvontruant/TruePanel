from pathlib import Path

from truepanel.hardware.bounded_automatic import (
    BoundedAutomaticLease,
)


def test_empty_commissioned_fingerprint_is_safe_locked():
    lease = BoundedAutomaticLease(
        commissioned_fingerprint="",
    )

    result = lease.start(
        current_fingerprint="1" * 64,
        active_profile="automatic",
        recommended_profile="balanced",
        telemetry_valid=True,
        telemetry_fresh=True,
        connected=True,
        safety_hold=False,
        recovery_pending=False,
    )

    assert result.accepted is False
    assert "commissioned safety fingerprint" in (
        result.message
    )
    assert lease.active() is False


def test_runtime_declares_bounded_automatic_contract():
    source = Path("lcd-menu.py").read_text(
        encoding="utf-8"
    )

    required = (
        "bounded_automatic_lease",
        "automatic_lease_started",
        "automatic_lease_expired",
        "automatic_lease_cancelled",
        "automatic_lease_safety_cancelled",
        "AUTOMATIC_LEASE_ALLOWED_PROFILES",
        "thermal_commissioned_fingerprint_match",
        "end_bounded_automatic_lease",
    )

    for value in required:
        assert value in source


def test_safety_tick_precedes_automatic_lease_checks():
    source = Path("lcd-menu.py").read_text(
        encoding="utf-8"
    )

    start = source.index(
        "def reconcile_fan_control"
    )
    end = source.index(
        "def set_thermal_operator_arm_state",
        start,
    )
    block = source[start:end]

    safety_tick = block.index(
        "fan_control_runtime.service.tick"
    )
    lease_check = block.index(
        "bounded_automatic_lease.deadline"
    )
    evaluation = block.index(
        "thermal_control_coordinator.evaluate"
    )

    assert safety_tick < lease_check < evaluation


def test_automatic_lease_envelope_excludes_afterburners():
    source = Path("lcd-menu.py").read_text(
        encoding="utf-8"
    )

    assert (
        "not in AUTOMATIC_LEASE_ALLOWED_PROFILES"
        in source
    )


def test_command_protocol_requires_explicit_confirmation():
    source = Path(
        "truepanel/hardware/fan_command.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "automatic_lease" in source
    assert (
        "ENGAGE_STAGE_2_AUTOMATIC_CONTROL"
        in source
    )


def test_status_bridge_carries_lease_fields_twice():
    source = Path(
        "truepanel/hardware/fan_status_bridge.py"
    ).read_text(
        encoding="utf-8"
    )

    assert source.count(
        '"thermal_automatic_lease_active"'
    ) == 4
    assert source.count(
        '"thermal_commissioned_fingerprint_match"'
    ) == 4


def test_web_snapshot_exposes_lease_fields():
    source = Path(
        "truepanel/web/snapshot.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "thermal_automatic_lease_active" in source
    assert "thermal_automatic_lease_remaining" in source
    assert (
        "thermal_commissioned_fingerprint_match"
        in source
    )


def test_production_default_has_no_commissioned_authority():
    source = Path(
        "truepanel/config/loader.py"
    ).read_text(
        encoding="utf-8"
    )

    assert '"commissioned_fingerprint": ""' in source


def test_runtime_authority_remains_ephemeral():
    source = Path("lcd-menu.py").read_text(
        encoding="utf-8"
    )

    assert "thermal_operator_armed = False" in source
    assert "thermal_dry_run = True" in source
    assert (
        "bounded_automatic_lease = "
        "BoundedAutomaticLease("
        in source
    )
