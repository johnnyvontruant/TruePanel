import json
from copy import deepcopy
from pathlib import Path

from truepanel.aegis.coverage import coverage_matrix
from truepanel.aegis.coverage_appraisal import (
    appraise_identity_coverage_candidate,
    load_identity_appraisal_policy,
    semantic_sha256,
)
from truepanel.aegis.identity_coverage import (
    build_identity_coverage_candidate,
    rehearse_identity_coverage_contract,
)
from truepanel.aegis.rehearsal import rehearse_recovery_paths
from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.holodeck.aegis_coverage_appraisal import (
    run_coverage_appraisal_rehearsal,
)

ROOT = Path(__file__).resolve().parents[1]


def _contracts():
    accepted = coverage_matrix(rehearse_recovery_paths())
    candidate = build_identity_coverage_candidate(
        accepted, rehearse_identity_coverage_contract()
    )
    return accepted, candidate


def test_exact_policy_bound_candidate_is_ready_only_for_independent_review():
    accepted, candidate = _contracts()

    result = appraise_identity_coverage_candidate(
        accepted_matrix=accepted,
        candidate=candidate,
    )

    assert result["status"] == "READY_FOR_INDEPENDENT_REVIEW"
    assert all(item["passed"] for item in result["conditions"])
    assert result["review_required"] is True
    assert result["independent_review_complete"] is False
    assert result["candidate_accepted"] is False
    assert result["candidate_installed"] is False
    assert result["automatic_acceptance"] is False
    assert result["production_mutation"] is False
    assert result["control_authority"] is False


def test_candidate_tampering_holds_even_if_attacker_recomputes_local_digest():
    accepted, candidate = _contracts()
    candidate["accepted"] = True
    candidate.pop("candidate_sha256")
    candidate["candidate_sha256"] = semantic_sha256(candidate)

    result = appraise_identity_coverage_candidate(
        accepted_matrix=accepted,
        candidate=candidate,
    )

    assert result["status"] == "HOLD"
    assert result["candidate_accepted"] is False
    assert any(not item["passed"] for item in result["conditions"])


def test_unknown_policy_or_candidate_fields_fail_closed():
    accepted, candidate = _contracts()
    policy = load_identity_appraisal_policy()
    policy["unreviewed"] = True

    policy_result = appraise_identity_coverage_candidate(
        accepted_matrix=accepted,
        candidate=candidate,
        policy=policy,
    )
    unknown_candidate = deepcopy(candidate)
    unknown_candidate["unreviewed"] = True
    unknown_candidate.pop("candidate_sha256")
    unknown_candidate["candidate_sha256"] = semantic_sha256(unknown_candidate)
    candidate_result = appraise_identity_coverage_candidate(
        accepted_matrix=accepted,
        candidate=unknown_candidate,
    )

    assert policy_result["status"] == "HOLD"
    assert candidate_result["status"] == "HOLD"


def test_malformed_evidence_counter_holds_instead_of_raising():
    accepted, candidate = _contracts()
    candidate["identity_rehearsal"]["measurements"]["false_outcomes"] = "zero"
    candidate["identity_rehearsal"].pop("evidence_sha256")
    candidate["identity_rehearsal"]["evidence_sha256"] = semantic_sha256(
        candidate["identity_rehearsal"]
    )
    candidate.pop("candidate_sha256")
    candidate["candidate_sha256"] = semantic_sha256(candidate)

    result = appraise_identity_coverage_candidate(
        accepted_matrix=accepted,
        candidate=candidate,
    )

    assert result["status"] == "HOLD"
    assert any(
        item["condition"] == "identity_evidence" and item["passed"] is False
        for item in result["conditions"]
    )


def test_holodeck_appraisal_challenges_every_binding_without_false_ready():
    report = run_coverage_appraisal_rehearsal()

    assert report["result"] == "PASS"
    assert report["measurements"] == {
        "scenarios": 6,
        "ready": 1,
        "holds": 5,
        "false_outcomes": 0,
        "false_ready": 0,
        "candidate_acceptances": 0,
        "runtime_writes": 0,
        "production_writes": 0,
    }
    assert report["safety"]["live_provider_access"] is False
    assert report["safety"]["control_authority"] is False


def test_preserved_appraisal_evidence_exactly_replays():
    expected = json.loads(
        (ROOT / "docs/evidence/aegis-identity-appraisal-v1.json").read_text()
    )
    assert run_coverage_appraisal_rehearsal() == expected


def test_mission_control_exposes_appraisal_without_changing_accepted_coverage():
    observed = AegisReliabilityEngine().observe(
        {"timestamp": 1.0, "operator_guidance": []}
    )
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()

    assert observed["coverage_matrix"]["schema_version"] == 1
    assert observed["coverage_appraisal"]["status"] == "READY_FOR_INDEPENDENT_REVIEW"
    assert observed["coverage_appraisal"]["candidate_accepted"] is False
    assert "Appraisal:" in source
    assert "Content bindings" in source
    assert "Independent review complete" in source
    assert "@media(max-width:760px)" in source
    assert "setInterval" not in source
