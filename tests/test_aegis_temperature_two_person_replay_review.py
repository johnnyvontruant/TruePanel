from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.temperature_two_person_replay_review import (
    DECISION_CONCUR,
    DECISION_DISSENT,
    NAMESPACE,
    REVIEWER_KEY_ID,
    pending_temperature_two_person_replay_review,
)
from truepanel.holodeck.aegis_temperature_two_person_replay_review import (
    run_temperature_two_person_replay_review_checkride,
)


def test_contract_requires_distinct_reviewer_and_choices():
    assert "two-person" in NAMESPACE
    assert REVIEWER_KEY_ID != "jt-development-review"
    assert {DECISION_CONCUR, DECISION_DISSENT} == {
        "CONCUR_ACCEPT_EVIDENCE",
        "DISSENT_HOLD_EVIDENCE",
    }


def test_pending_path_fails_closed_without_primary_acceptance():
    result = pending_temperature_two_person_replay_review(
        {"review_recorded": False, "manual_calibration_consideration": False}
    )
    assert result["status"] == "HOLD"
    assert result["two_person_quorum"] is False
    assert result["deployment_authority"] is False


def test_holodeck_proves_quorum_and_negative_authority():
    measurements = run_temperature_two_person_replay_review_checkride()["measurements"]
    assert measurements["scenario_count"] == 5
    assert measurements["quorum_count"] == 1
    assert measurements["operator_hold_count"] == 1
    assert measurements["independent_reviewers"] == 2
    assert measurements["lead_samples"] == 27
    assert (
        measurements["field_validations"]
        == measurements["deployments"]
        == measurements["hardware_actions"]
        == 0
    )


def test_mission_control_exposes_quorum_gate():
    payload = AegisReliabilityEngine().observe({"timestamp": 0.0})
    review = payload["coverage_two_person_replay_review"]
    assert review["status"] == "HOLD"
    assert review["two_person_quorum"] is False


def test_mobile_copy_names_concurrence_boundary():
    with open("truepanel/web/static/reliability-view.js", encoding="utf-8") as stream:
        source = stream.read()
    assert "Two-Person Replay Review" in source
    assert "CONCUR or DISSENT" in source
