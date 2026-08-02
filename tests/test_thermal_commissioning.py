from truepanel.hardware.thermal_commissioning import (
    THERMAL_COMMISSIONING_STATES,
    thermal_commissioning_state,
)


def classify(
    *,
    mode="observe_only",
    armed=False,
    dry_run=True,
    supervised=False,
):
    return thermal_commissioning_state(
        policy_mode=mode,
        operator_armed=armed,
        dry_run=dry_run,
        supervised_session_active=supervised,
    )


def test_state_vocabulary_is_stable():
    assert THERMAL_COMMISSIONING_STATES == (
        "configured",
        "dry_run_armed",
        "supervised_live",
        "commissioned_disarmed",
    )


def test_supervised_live_has_highest_precedence():
    assert classify(
        mode="automatic_control",
        armed=True,
        dry_run=False,
        supervised=True,
    ) == "supervised_live"


def test_armed_dry_run_is_reported():
    assert classify(
        mode="automatic_control",
        armed=True,
        dry_run=True,
    ) == "dry_run_armed"


def test_commissioned_disarmed_is_reported():
    assert classify(
        mode="automatic_control",
        armed=False,
        dry_run=True,
    ) == "commissioned_disarmed"


def test_observe_only_is_configured():
    assert classify(
        mode="observe_only",
        armed=False,
        dry_run=True,
    ) == "configured"


def test_unsupervised_live_flags_do_not_claim_live_session():
    assert classify(
        mode="automatic_control",
        armed=True,
        dry_run=False,
        supervised=False,
    ) == "commissioned_disarmed"
