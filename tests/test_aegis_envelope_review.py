import json
from copy import deepcopy
from pathlib import Path

from truepanel.aegis.envelope_review import (
    build_envelope_review_packet,
    prepare_envelope_review_handoff,
    validate_envelope_review_packet,
)
from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.holodeck.aegis_envelope_review import (
    _materials,
    run_envelope_review_rehearsal,
)

ROOT = Path(__file__).resolve().parents[1]


def test_unsigned_runtime_cannot_cross_envelope_review_boundary():
    observed = AegisReliabilityEngine().observe(
        {"timestamp": 1.0, "operator_guidance": []}
    )
    review = observed["coverage_envelope_review"]

    assert review["status"] == "HOLD"
    assert review["reason"] == "EnvelopeDraftNotReviewable"
    assert review["valid_reviewer_count"] == 0
    assert review["manual_acceptance_required"] is True
    assert review["envelope_accepted"] is False
    assert review["envelope_installed"] is False
    assert review["control_authority"] is False


def test_packet_rejects_unknown_fields_and_draft_substitution():
    material = _materials()
    packet = build_envelope_review_packet(**material)
    extended = deepcopy(packet)
    extended["presentation_note"] = "unsigned"
    substituted = deepcopy(material)
    substituted["draft_result"] = deepcopy(material["draft_result"])
    substituted["draft_result"]["draft"]["expires_at"] = "2027-01-01T00:00:00Z"

    extended_failures = validate_envelope_review_packet(extended, **material)
    substituted_failures = validate_envelope_review_packet(packet, **substituted)

    assert "EnvelopeReviewPacketShapeInvalid" in extended_failures
    assert "EnvelopeDraftNotReviewable" in substituted_failures
    assert "EnvelopeReviewSubjectBindingInvalid" in substituted_failures


def test_reviewable_draft_handoff_still_requires_external_signatures():
    material = _materials()
    result = prepare_envelope_review_handoff(**material)

    assert result["status"] == "AWAITING_INDEPENDENT_ENVELOPE_SIGNATURES"
    assert result["production_keys_present"] is False
    assert result["independent_review_complete"] is False
    assert result["envelope_accepted"] is False
    assert result["automatic_acceptance"] is False


def test_holodeck_envelope_review_has_no_false_eligible_path():
    report = run_envelope_review_rehearsal()

    assert report["result"] == "PASS"
    assert report["measurements"] == {
        "scenarios": 10,
        "eligible": 1,
        "holds": 9,
        "false_outcomes": 0,
        "false_eligible": 0,
        "envelopes_accepted": 0,
        "envelopes_installed": 0,
        "candidate_acceptances": 0,
        "runtime_writes": 0,
        "production_writes": 0,
    }
    assert report["safety"]["production_keys"] == 0
    assert report["safety"]["manual_acceptance_required"] is True
    assert report["safety"]["control_authority"] is False


def test_preserved_envelope_review_evidence_replays_exactly():
    expected = json.loads(
        (ROOT / "docs/evidence/aegis-envelope-review-v1.json").read_text()
    )
    assert run_envelope_review_rehearsal() == expected


def test_mission_control_exposes_manual_acceptance_boundary_on_mobile():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()

    assert "coverage_envelope_review" in source
    assert "Envelope review" in source
    assert "Manual acceptance required" in source
    assert "Envelope accepted" in source
    assert "Installed" in source
    assert "@media(max-width:760px)" in source
    assert "setInterval" not in source
