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


def test_commissioning_accepts_bounded_automatic_actions():
    from truepanel.history.thermal_commissioning import (
        commissioning_event,
    )

    actions = (
        "automatic_lease_started",
        "automatic_lease_cancelled",
        "automatic_lease_expired",
        "automatic_lease_safety_cancelled",
    )

    for action in actions:
        event = commissioning_event(
            lifecycle_action=action,
            reason="Stage 1 lifecycle test.",
            commissioning_state="commissioned_disarmed",
            active_profile="automatic",
            control_authority="automatic",
            lease_remaining=0.0,
        )

        assert event["lifecycle_action"] == action


def test_commissioning_history_persists_automatic_lease(
    tmp_path,
):
    from truepanel.history.thermal_commissioning import (
        ThermalCommissioningHistory,
        commissioning_event,
    )

    history = ThermalCommissioningHistory(
        tmp_path / "thermal-commissioning.jsonl"
    )

    history.append(
        commissioning_event(
            lifecycle_action="automatic_lease_started",
            reason="Bounded automatic control started.",
            commissioning_state="automatic_lease",
            active_profile="balanced",
            control_authority="manual",
            lease_remaining=600.0,
        )
    )

    history.append(
        commissioning_event(
            lifecycle_action="automatic_lease_cancelled",
            reason="Bounded automatic control cancelled.",
            commissioning_state="commissioned_disarmed",
            active_profile="automatic",
            control_authority="automatic",
            lease_remaining=0.0,
        )
    )

    events = history.read(limit=10)

    assert [
        event["lifecycle_action"]
        for event in events
    ] == [
        "automatic_lease_started",
        "automatic_lease_cancelled",
    ]
