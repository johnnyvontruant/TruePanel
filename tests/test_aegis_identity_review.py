import json
from copy import deepcopy
from pathlib import Path

from truepanel.aegis.coverage import coverage_matrix
from truepanel.aegis.coverage_appraisal import appraise_identity_coverage_candidate
from truepanel.aegis.coverage_review import (
    build_identity_review_packet,
    prepare_identity_review_handoff,
    validate_identity_review_packet,
)
from truepanel.aegis.identity_coverage import (
    build_identity_coverage_candidate,
    rehearse_identity_coverage_contract,
)
from truepanel.aegis.rehearsal import rehearse_recovery_paths
from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.holodeck.aegis_identity_review import run_identity_review_rehearsal

ROOT = Path(__file__).resolve().parents[1]


def _materials():
    accepted = coverage_matrix(rehearse_recovery_paths())
    candidate = build_identity_coverage_candidate(
        accepted, rehearse_identity_coverage_contract()
    )
    appraisal = appraise_identity_coverage_candidate(
        accepted_matrix=accepted, candidate=candidate
    )
    packet = build_identity_review_packet(
        accepted_matrix=accepted,
        candidate=candidate,
        appraisal=appraisal,
    )
    return accepted, candidate, appraisal, packet


def test_review_packet_binds_exact_appraised_candidate_without_authority():
    accepted, candidate, appraisal, packet = _materials()

    assert validate_identity_review_packet(
        packet,
        accepted_matrix=accepted,
        candidate=candidate,
        appraisal=appraisal,
    ) == ()
    handoff = prepare_identity_review_handoff(
        accepted_matrix=accepted,
        candidate=candidate,
        appraisal=appraisal,
    )
    assert handoff["status"] == "AWAITING_INDEPENDENT_SIGNATURES"
    assert handoff["production_keys_present"] is False
    assert handoff["candidate_accepted"] is False
    assert handoff["successor_envelope_created"] is False
    assert handoff["control_authority"] is False


def test_packet_or_subject_drift_holds():
    accepted, candidate, appraisal, packet = _materials()

    changed_packet = deepcopy(packet)
    changed_packet["unreviewed"] = True
    changed_candidate = deepcopy(candidate)
    changed_candidate["accepted"] = True

    assert validate_identity_review_packet(
        changed_packet,
        accepted_matrix=accepted,
        candidate=candidate,
        appraisal=appraisal,
    )
    assert validate_identity_review_packet(
        packet,
        accepted_matrix=accepted,
        candidate=changed_candidate,
        appraisal=appraisal,
    )


def test_holodeck_review_rehearsal_has_no_false_eligible_path():
    report = run_identity_review_rehearsal()

    assert report["result"] == "PASS"
    assert report["measurements"] == {
        "scenarios": 9,
        "eligible": 1,
        "holds": 8,
        "false_outcomes": 0,
        "false_eligible": 0,
        "candidate_acceptances": 0,
        "successor_envelopes_created": 0,
        "runtime_writes": 0,
        "production_writes": 0,
    }
    assert report["safety"]["production_keys"] == 0
    assert report["safety"]["control_authority"] is False


def test_preserved_identity_review_evidence_replays_exactly():
    expected = json.loads(
        (ROOT / "docs/evidence/aegis-identity-review-v1.json").read_text()
    )
    assert run_identity_review_rehearsal() == expected


def test_mission_control_exposes_unsigned_review_boundary():
    observed = AegisReliabilityEngine().observe(
        {"timestamp": 1.0, "operator_guidance": []}
    )
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()

    assert observed["coverage_matrix"]["schema_version"] == 1
    assert observed["coverage_review"]["status"] == "AWAITING_INDEPENDENT_SIGNATURES"
    assert observed["coverage_review"]["candidate_accepted"] is False
    assert observed["coverage_review"]["production_keys_present"] is False
    assert "Review handoff" in source
    assert "Production keys present" in source
    assert "Successor envelope created" in source
    assert "@media(max-width:760px)" in source
    assert "setInterval" not in source
