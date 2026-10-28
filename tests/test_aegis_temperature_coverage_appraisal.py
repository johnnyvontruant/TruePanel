from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from truepanel.aegis.coverage import coverage_matrix
from truepanel.aegis.rehearsal import rehearse_recovery_paths
from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.temperature_coverage import (
    build_temperature_coverage_candidate,
    rehearse_temperature_coverage,
)
from truepanel.aegis.temperature_coverage_appraisal import (
    PINNED_SUBJECTS,
    appraise_temperature_coverage,
    temperature_coverage_implementation_sha256,
)
from truepanel.holodeck.aegis_temperature_blind_spot import (
    run_temperature_blind_spot_checkride,
)
from truepanel.holodeck.aegis_temperature_coverage_appraisal import (
    run_temperature_coverage_appraisal_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def _subjects():
    accepted = coverage_matrix(rehearse_recovery_paths())
    evidence = run_temperature_blind_spot_checkride()
    candidate = build_temperature_coverage_candidate(
        accepted, rehearse_temperature_coverage()
    )
    implementation = temperature_coverage_implementation_sha256(
        run_temperature_blind_spot_checkride
    )
    return accepted, candidate, evidence, implementation


def test_exact_temperature_candidate_is_only_ready_for_independent_review():
    accepted, candidate, evidence, implementation = _subjects()
    result = appraise_temperature_coverage(
        accepted,
        candidate,
        evidence,
        implementation_sha256=implementation,
    )

    assert result["status"] == "READY_FOR_INDEPENDENT_REVIEW"
    assert result["ready_for_independent_review"] is True
    assert result["accepted"] is False
    assert result["installed"] is False
    assert result["automatic_acceptance"] is False
    assert result["runtime_authority"] is False
    assert result["production_authority"] is False
    assert result["hardware_authority"] is False
    assert result["subjects"] == PINNED_SUBJECTS
    assert result["coverage"] == {
        "accepted": "8/8 trusted",
        "candidate": "9/9 rehearsed",
        "candidate_gap_count": 0,
    }


def test_self_consistent_candidate_tamper_still_holds():
    accepted, candidate, evidence, implementation = _subjects()
    candidate["entries"][-1]["title"] = "Unreviewed title"
    candidate.pop("candidate_sha256")
    import hashlib

    candidate["candidate_sha256"] = hashlib.sha256(
        json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    result = appraise_temperature_coverage(
        accepted,
        candidate,
        evidence,
        implementation_sha256=implementation,
    )
    assert result["status"] == "HOLD"
    assert result["ready_for_independent_review"] is False
    assert "candidate_document_sha256 does not match the reviewed subject" in result["errors"]
    assert "candidate does not match independent reconstruction" in result["errors"]


def test_evidence_substitution_predecessor_and_implementation_drift_hold():
    accepted, candidate, evidence, implementation = _subjects()

    predecessor = deepcopy(accepted)
    predecessor["entries"][0]["title"] += " drift"
    assert appraise_temperature_coverage(
        predecessor,
        candidate,
        evidence,
        implementation_sha256=implementation,
    )["status"] == "HOLD"

    substitute = deepcopy(evidence)
    substitute["scenario"] = "other-valid-looking-proof"
    assert appraise_temperature_coverage(
        accepted,
        candidate,
        substitute,
        implementation_sha256=implementation,
    )["status"] == "HOLD"

    assert appraise_temperature_coverage(
        accepted,
        candidate,
        evidence,
        implementation_sha256="0" * 64,
    )["status"] == "HOLD"


def test_holodeck_appraisal_has_one_ready_and_nine_holds():
    report = run_temperature_coverage_appraisal_checkride()

    assert report["simulation"] is True
    assert report["hardware_isolated"] is True
    assert report["production_mutation"] is False
    assert report["control_authority"] is False
    assert report["measurements"] == {
        "scenario_count": 10,
        "review_ready_count": 1,
        "hold_count": 9,
        "unsafe_ready_count": 0,
        "candidate_acceptances": 0,
        "candidate_installations": 0,
        "runtime_writes": 0,
        "hardware_actions": 0,
    }


def test_preserved_temperature_appraisal_evidence_replays_exactly():
    preserved = json.loads(
        (ROOT / "docs/evidence/aegis-temperature-coverage-appraisal-v1.json").read_text()
    )
    assert preserved == run_temperature_coverage_appraisal_checkride()


def test_engine_exposes_review_only_appraisal_without_changing_accepted_matrix():
    result = AegisReliabilityEngine().observe({"operator_guidance": []})

    assert result["coverage_summary"] == {"total": 8, "trusted": 8, "gaps": 0}
    assert result["coverage_candidate"]["total"] == 9
    assert result["coverage_appraisal"]["status"] == "READY_FOR_INDEPENDENT_REVIEW"
    assert result["coverage_appraisal"]["accepted"] is False
    assert result["coverage_appraisal"]["runtime_authority"] is False


def test_mobile_mission_control_exposes_appraisal_and_authority_boundaries():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()

    assert "Candidate Appraisal" in source
    assert "Ready only for a separate independent review" in source
    assert "Runtime authority:" in source
    assert "Hardware authority:" in source
    assert "@media(max-width:760px)" in source
