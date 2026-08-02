import copy

import pytest

from truepanel.hardware.bounded_automatic import (
    AUTOMATIC_LEASE_ALLOWED_PROFILES,
    AUTOMATIC_LEASE_SECONDS,
    BoundedAutomaticLease,
    thermal_safety_contract,
    thermal_safety_fingerprint,
)


class FakeClock:
    def __init__(self, value=100.0):
        self.value = float(value)

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += float(seconds)


def config():
    return {
        "theme_pack": "tactical",
        "hardware": {
            "fan_control": {
                "enabled": True,
                "command_timeout": 300,
                "afterburners_timeout": 120,
                "safety_recovery_cycles": 3,
                "profiles": {
                    "quiet": {
                        "pwm": 170,
                        "timeout": 300,
                    },
                    "balanced": {
                        "pwm": 194,
                        "timeout": 300,
                    },
                    "cooling_boost": {
                        "pwm": 225,
                        "timeout": 300,
                    },
                    "afterburners": {
                        "pwm": 255,
                        "timeout": 120,
                    },
                },
                "controlled_channels": [1, 2],
            },
            "thermal_policy": {
                "mode": "automatic_control",
                "operator_armed": True,
                "dry_run": True,
                "command_cooldown_seconds": 30,
                "balanced_temperature_c": 42,
                "cooling_boost_temperature_c": 50,
                "afterburners_temperature_c": 60,
                "hysteresis_c": 3,
                "minimum_dwell_seconds": 30,
            },
        },
    }


def start_kwargs(fingerprint):
    return {
        "current_fingerprint": fingerprint,
        "active_profile": "automatic",
        "recommended_profile": "balanced",
        "telemetry_valid": True,
        "telemetry_fresh": True,
        "connected": True,
        "safety_hold": False,
        "recovery_pending": False,
    }


def test_default_lease_is_twenty_four_hours():
    assert AUTOMATIC_LEASE_SECONDS == 86400.0


def test_profile_envelope_excludes_quiet_and_afterburners():
    assert AUTOMATIC_LEASE_ALLOWED_PROFILES == {
        "balanced",
        "cooling_boost",
    }


def test_fingerprint_ignores_unrelated_display_configuration():
    original = config()
    changed = copy.deepcopy(original)
    changed["theme_pack"] = "default"
    changed["flightdeck"] = {
        "rotation_interval": 99,
    }

    assert (
        thermal_safety_fingerprint(original)
        == thermal_safety_fingerprint(changed)
    )


def test_fingerprint_ignores_runtime_authorization_flags():
    original = config()
    changed = copy.deepcopy(original)
    changed["hardware"]["thermal_policy"][
        "operator_armed"
    ] = False
    changed["hardware"]["thermal_policy"][
        "dry_run"
    ] = False

    assert (
        thermal_safety_fingerprint(original)
        == thermal_safety_fingerprint(changed)
    )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (
            ("hardware", "fan_control", "controlled_channels"),
            [1],
        ),
        (
            ("hardware", "fan_control", "profiles"),
            {
                "balanced": {
                    "pwm": 180,
                    "timeout": 300,
                }
            },
        ),
        (
            (
                "hardware",
                "thermal_policy",
                "cooling_boost_temperature_c",
            ),
            55,
        ),
    ],
)
def test_fingerprint_changes_for_safety_configuration(
    path,
    value,
):
    original = config()
    changed = copy.deepcopy(original)

    destination = changed
    for key in path[:-1]:
        destination = destination[key]
    destination[path[-1]] = value

    assert (
        thermal_safety_fingerprint(original)
        != thermal_safety_fingerprint(changed)
    )


def test_contract_contains_no_theme_or_runtime_arm_flags():
    contract = thermal_safety_contract(config())

    assert "theme_pack" not in contract
    policy = contract["hardware"]["thermal_policy"]
    assert "operator_armed" not in policy
    assert "dry_run" not in policy


def test_lease_starts_from_safe_commissioned_state():
    fingerprint = thermal_safety_fingerprint(config())
    clock = FakeClock()
    lease = BoundedAutomaticLease(
        commissioned_fingerprint=fingerprint,
        clock=clock,
    )

    decision = lease.start(
        **start_kwargs(fingerprint)
    )

    assert decision.accepted is True
    assert decision.status == "automatic_lease"
    assert lease.active() is True
    assert lease.remaining_seconds() == 86400.0


def test_lease_expires_without_persistent_authority():
    fingerprint = thermal_safety_fingerprint(config())
    clock = FakeClock()
    lease = BoundedAutomaticLease(
        commissioned_fingerprint=fingerprint,
        clock=clock,
    )
    lease.start(**start_kwargs(fingerprint))

    clock.advance(86400)

    assert lease.active() is False
    assert lease.remaining_seconds() == 0.0


def test_cancel_clears_deadline():
    fingerprint = thermal_safety_fingerprint(config())
    lease = BoundedAutomaticLease(
        commissioned_fingerprint=fingerprint,
    )
    lease.start(**start_kwargs(fingerprint))

    assert lease.cancel() is True
    assert lease.active() is False
    assert lease.cancel() is False


@pytest.mark.parametrize(
    ("field", "value", "fragment"),
    [
        (
            "current_fingerprint",
            "0" * 64,
            "commissioned safety fingerprint",
        ),
        (
            "active_profile",
            "balanced",
            "motherboard automatic mode",
        ),
        (
            "recommended_profile",
            "quiet",
            "profile envelope",
        ),
        (
            "recommended_profile",
            "afterburners",
            "profile envelope",
        ),
        (
            "telemetry_valid",
            False,
            "telemetry is invalid",
           ),
        (
            "telemetry_fresh",
            False,
            "telemetry is stale",
           ),
        (
            "connected",
            False,
            "runtime is disconnected",
        ),
        (
            "safety_hold",
            True,
            "safety hold is active",
           ),
        (
            "recovery_pending",
            True,
            "recovery is pending",
       ),
    ],
)
def test_start_blocks_each_safety_failure(
    field,
    value,
    fragment,
):
    fingerprint = thermal_safety_fingerprint(config())
    lease = BoundedAutomaticLease(
        commissioned_fingerprint=fingerprint,
    )
    kwargs = start_kwargs(fingerprint)
    kwargs[field] = value

    decision = lease.start(**kwargs)

    assert decision.accepted is False
    assert decision.status == "readiness_blocked"
    assert fragment in decision.message
    assert lease.active() is False


def test_invalid_duration_is_rejected():
    with pytest.raises(
        ValueError,
        match="duration",
    ):
        BoundedAutomaticLease(
            commissioned_fingerprint="1" * 64,
            duration_seconds=0,
        )


def test_invalid_fingerprint_is_rejected():
    with pytest.raises(
        ValueError,
        match="fingerprint",
    ):
        BoundedAutomaticLease(
            commissioned_fingerprint="not-a-digest",
        )


def test_module_contains_no_hardware_write_path():
    source = (
        __import__(
            "pathlib"
        )
        .Path(
            "truepanel/hardware/bounded_automatic.py"
        )
        .read_text(
            encoding="utf-8"
        )
    )

    for forbidden in (
        "request_profile",
        "FanHardwareExecutor",
        "set_manual_pwm",
        "write_int",
        "/sys/",
    ):
        assert forbidden not in source


def test_contract_fingerprints_stage_three_authorization():
    contract = thermal_safety_contract(
        config()
    )

    authorization = contract[
        "bounded_automatic_authorization"
    ]

    assert authorization == {
        "stage": 3,
        "lease_seconds": 86400.0,
        "allowed_profiles": [
            "balanced",
            "cooling_boost",
        ],
    }


def test_stage_two_authorization_changes_old_fingerprint():
    current = thermal_safety_contract(
        config()
    )

    legacy = copy.deepcopy(current)
    legacy[
        "bounded_automatic_authorization"
    ] = {
        "stage": 1,
        "lease_seconds": 600.0,
        "allowed_profiles": [
            "balanced",
            "cooling_boost",
        ],
    }

    import hashlib
    import json

    current_digest = hashlib.sha256(
        json.dumps(
            current,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()

    legacy_digest = hashlib.sha256(
        json.dumps(
            legacy,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()

    assert current_digest != legacy_digest


def test_stage_three_lease_is_twenty_four_hours():
    assert AUTOMATIC_LEASE_SECONDS == 86400.0

    contract = thermal_safety_contract(
        config()
    )

    assert contract[
        "bounded_automatic_authorization"
    ]["stage"] == 3

    assert contract[
        "bounded_automatic_authorization"
    ]["lease_seconds"] == 86400.0


def test_active_lease_can_be_renewed():
    fingerprint = thermal_safety_fingerprint(
        config()
    )
    clock = FakeClock()
    lease = BoundedAutomaticLease(
        commissioned_fingerprint=fingerprint,
        clock=clock,
    )

    started = lease.start(
        **start_kwargs(fingerprint)
    )

    assert started.accepted is True

    clock.advance(120)

    decision = lease.renew(
        current_fingerprint=fingerprint,
        active_profile="balanced",
        recommended_profile="balanced",
        telemetry_valid=True,
        telemetry_fresh=True,
        connected=True,
        safety_hold=False,
        recovery_pending=False,
    )

    assert decision.accepted is True
    assert decision.status == (
        "automatic_lease_renewed"
    )
    assert lease.remaining_seconds() == 86400.0


def test_inactive_lease_cannot_be_renewed():
    fingerprint = thermal_safety_fingerprint(
        config()
    )
    lease = BoundedAutomaticLease(
        commissioned_fingerprint=fingerprint,
    )

    decision = lease.renew(
        current_fingerprint=fingerprint,
        active_profile="balanced",
        recommended_profile="balanced",
        telemetry_valid=True,
        telemetry_fresh=True,
        connected=True,
        safety_hold=False,
        recovery_pending=False,
    )

    assert decision.accepted is False
    assert decision.status == "renewal_blocked"
    assert "active automatic lease" in decision.message


def test_renewal_rejects_profile_outside_envelope():
    fingerprint = thermal_safety_fingerprint(
        config()
    )
    lease = BoundedAutomaticLease(
        commissioned_fingerprint=fingerprint,
    )

    lease.start(
        **start_kwargs(fingerprint)
    )

    decision = lease.renew(
        current_fingerprint=fingerprint,
        active_profile="afterburners",
        recommended_profile="balanced",
        telemetry_valid=True,
        telemetry_fresh=True,
        connected=True,
        safety_hold=False,
        recovery_pending=False,
    )

    assert decision.accepted is False
    assert "approved automatic-control envelope" in (
        decision.message
        + " "
        + " ".join(decision.blocking_reasons)
    )
