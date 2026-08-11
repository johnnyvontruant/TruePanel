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

    combined = runtime + authority

    required = (
        "automatic_lease_started",
        "automatic_lease_expired",
        "automatic_lease_cancelled",
        "automatic_lease_safety_cancelled",
        "AUTOMATIC_LEASE_ALLOWED_PROFILES",
        "thermal_commissioned_fingerprint_match",
        "end_bounded_automatic_lease",
    )

    for value in required:
        assert value in combined

    assert (
        "self.automatic_lease"
        in authority
    )

def test_safety_tick_precedes_automatic_lease_checks():
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

    start = runtime.index(
        "def reconcile_fan_control"
    )

    end = runtime.index(
        "def set_thermal_operator_arm_state",
        start,
    )

    block = runtime[start:end]

    safety_tick = block.index(
        "fan_control_runtime.service.tick"
    )

    thermal_reconcile = block.index(
        "thermal_authority.reconcile("
    )

    assert safety_tick < thermal_reconcile

    host_start = authority.index(
        "def reconcile("
    )

    host_end = authority.index(
        "def handle_action(",
        host_start,
    )

    host_reconcile = authority[
        host_start:host_end
    ]

    assert (
        "self.automatic_lease.deadline"
        in host_reconcile
    )

def test_automatic_lease_envelope_excludes_afterburners():
    authority = Path(
        "truepanel/host/thermal_authority.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "not in AUTOMATIC_LEASE_ALLOWED_PROFILES"
        in authority
    )

    assert (
        "approved profile envelope"
        in authority
    )

def test_command_protocol_requires_explicit_confirmation():
    source = Path(
        "truepanel/hardware/fan_command.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "automatic_lease" in source
    assert (
        "ENGAGE_STAGE_3_AUTOMATIC_CONTROL"
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
        "host_bootstrap.thermal_authority"
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
        "self.operator_armed = False"
        in authority
    )

    assert (
        "self.dry_run = True"
        in authority
    )

def test_stage_three_runtime_supports_renewal():
    authority = Path(
        "truepanel/host/thermal_authority.py"
    ).read_text(
        encoding="utf-8"
    )

    command = Path(
        "truepanel/hardware/fan_command.py"
    ).read_text(
        encoding="utf-8"
    )

    server = Path(
        "truepanel/web/server.py"
    ).read_text(
        encoding="utf-8"
    )

    history = Path(
        "truepanel/history/thermal_commissioning.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "automatic_lease_renew" in authority

    assert (
        "self.automatic_lease.renew("
        in authority
    )

    assert "automatic_lease_renew" in command
    assert "automatic_lease_renew" in server
    assert "automatic_lease_renewed" in history
