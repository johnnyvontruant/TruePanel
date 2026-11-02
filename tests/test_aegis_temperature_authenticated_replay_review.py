from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.temperature_authenticated_replay_review import (
    DECISION_ACCEPT,
    DECISION_HOLD,
    NAMESPACE,
    pending_temperature_authenticated_replay_review,
)
from truepanel.holodeck.aegis_temperature_authenticated_replay_review import (
    run_temperature_authenticated_replay_review_checkride,
)


def test_contract_is_distinct_and_exclusive():
    assert "authenticated-replay-review" in NAMESPACE
    assert {DECISION_ACCEPT, DECISION_HOLD} == {"ACCEPT_EVIDENCE", "HOLD_EVIDENCE"}


def test_live_path_fails_closed():
    result = pending_temperature_authenticated_replay_review(
        {"replay_receipt_written": False}
    )
    assert result["status"] == "HOLD"
    assert result["manual_calibration_consideration"] is False
    assert result["deployment_authority"] is False


def test_holodeck_proves_review_and_safety_boundaries():
    measurements = run_temperature_authenticated_replay_review_checkride()[
        "measurements"
    ]
    assert measurements["scenario_count"] == 6
    assert measurements["accepted_count"] == 1
    assert measurements["operator_hold_count"] == 1
    assert measurements["adversarial_hold_count"] == 3
    assert measurements["lead_samples"] == 27
    assert (
        measurements["field_validations"]
        == measurements["deployments"]
        == measurements["hardware_actions"]
        == 0
    )


def test_mission_control_exposes_review_gate():
    payload = AegisReliabilityEngine().observe({"timestamp": 0.0})
    review = payload["coverage_authenticated_replay_review"]
    assert review["status"] == "HOLD"
    assert review["field_validated"] is False


def test_mobile_copy_names_exact_decisions():
    with open("truepanel/web/static/reliability-view.js", encoding="utf-8") as stream:
        source = stream.read()
    assert "Authenticated Replay Review" in source
    assert "ACCEPT_EVIDENCE or HOLD_EVIDENCE" in source
