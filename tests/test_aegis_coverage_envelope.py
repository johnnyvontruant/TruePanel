import json
from copy import deepcopy
from pathlib import Path

from truepanel.aegis.assurance import load_assurance_envelope
from truepanel.aegis.coverage import coverage_matrix
from truepanel.aegis.coverage_appraisal import (
    appraise_identity_coverage_candidate,
    semantic_sha256,
)
from truepanel.aegis.coverage_envelope import prepare_coverage_successor_draft
from truepanel.aegis.coverage_review import (
    REVIEW_RECEIPT_SCHEMA,
    build_identity_review_packet,
    prepare_identity_review_handoff,
)
from truepanel.aegis.identity_coverage import (
    build_identity_coverage_candidate,
    rehearse_identity_coverage_contract,
)
from truepanel.aegis.rehearsal import rehearse_recovery_paths
from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.holodeck.aegis_coverage_envelope import (
    run_coverage_envelope_rehearsal,
)

ROOT = Path(__file__).resolve().parents[1]


def _unsigned_materials():
    accepted = coverage_matrix(rehearse_recovery_paths())
    candidate = build_identity_coverage_candidate(
        accepted, rehearse_identity_coverage_contract()
    )
    appraisal = appraise_identity_coverage_candidate(
        accepted_matrix=accepted, candidate=candidate
    )
    handoff = prepare_identity_review_handoff(
        accepted_matrix=accepted,
        candidate=candidate,
        appraisal=appraisal,
    )
    return accepted, candidate, appraisal, handoff


def test_unsigned_runtime_handoff_cannot_create_envelope_draft():
    accepted, candidate, appraisal, handoff = _unsigned_materials()
    result = prepare_coverage_successor_draft(
        accepted_envelope=load_assurance_envelope(),
        accepted_matrix=accepted,
        candidate_matrix=candidate,
        appraisal=appraisal,
        review_result=handoff,
        issued_at="2026-09-18T04:05:00Z",
        expires_at="2026-12-15T04:05:00Z",
    )

    assert result["status"] == "HOLD"
    assert result["reason"] == "IndependentReviewRequired"
    assert result["draft"] is None
    assert result["successor_envelope_created"] is False
    assert result["candidate_accepted"] is False
    assert result["control_authority"] is False


def test_candidate_or_appraisal_change_cannot_cross_review_boundary():
    accepted, candidate, appraisal, _handoff = _unsigned_materials()
    eligible = {
        "schema": REVIEW_RECEIPT_SCHEMA,
        "status": "ELIGIBLE_FOR_SUCCESSOR_ENVELOPE_DRAFT",
        "reason": "IndependentCoverageReviewVerified",
        "packet_sha256": semantic_sha256(
            build_identity_review_packet(
                accepted_matrix=accepted,
                candidate=candidate,
                appraisal=appraisal,
            )
        ),
        "receipt_sha256": "b" * 64,
        "valid_reviewer_count": 2,
        "candidate_accepted": False,
        "successor_envelope_created": False,
        "automatic_acceptance": False,
        "control_authority": False,
    }
    changed_candidate = deepcopy(candidate)
    changed_candidate["accepted"] = True
    changed_appraisal = deepcopy(appraisal)
    changed_appraisal["status"] = "HOLD"

    candidate_result = prepare_coverage_successor_draft(
        accepted_envelope=load_assurance_envelope(),
        accepted_matrix=accepted,
        candidate_matrix=changed_candidate,
        appraisal=appraisal,
        review_result=eligible,
        issued_at="2026-09-18T04:05:00Z",
        expires_at="2026-12-15T04:05:00Z",
    )
    appraisal_result = prepare_coverage_successor_draft(
        accepted_envelope=load_assurance_envelope(),
        accepted_matrix=accepted,
        candidate_matrix=candidate,
        appraisal=changed_appraisal,
        review_result=eligible,
        issued_at="2026-09-18T04:05:00Z",
        expires_at="2026-12-15T04:05:00Z",
    )

    assert candidate_result["status"] == "HOLD"
    assert appraisal_result["status"] == "HOLD"


def test_holodeck_envelope_checkride_has_no_false_ready_path():
    report = run_coverage_envelope_rehearsal()

    assert report["result"] == "PASS"
    assert report["measurements"] == {
        "scenarios": 9,
        "ready": 1,
        "holds": 8,
        "false_outcomes": 0,
        "false_ready": 0,
        "draft_artifacts_created": 1,
        "envelopes_accepted": 0,
        "envelopes_installed": 0,
        "runtime_writes": 0,
        "production_writes": 0,
    }
    assert report["safety"]["production_keys"] == 0
    assert report["safety"]["control_authority"] is False


def test_preserved_envelope_evidence_replays_exactly():
    expected = json.loads(
        (ROOT / "docs/evidence/aegis-coverage-envelope-v1.json").read_text()
    )
    assert run_coverage_envelope_rehearsal() == expected


def test_mission_control_exposes_blocked_envelope_draft_boundary():
    observed = AegisReliabilityEngine().observe(
        {"timestamp": 1.0, "operator_guidance": []}
    )
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()

    assert observed["coverage_matrix"]["schema_version"] == 1
    assert observed["coverage_envelope_draft"]["status"] == "HOLD"
    assert observed["coverage_envelope_draft"]["draft"] is None
    assert observed["coverage_envelope_draft"]["candidate_accepted"] is False
    assert "Envelope draft" in source
    assert "Envelope accepted" in source
    assert "@media(max-width:760px)" in source
    assert "setInterval" not in source
