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
    appraise_temperature_coverage,
    temperature_coverage_implementation_sha256,
)
from truepanel.aegis.temperature_development_acceptance import (
    CONFIRMATION_SCHEMA,
    OPERATOR_ID,
    REQUIRED_STATEMENT,
    SCOPE,
    evaluate_temperature_development_acceptance,
    prepare_temperature_development_acceptance,
)
from truepanel.holodeck.aegis_temperature_blind_spot import (
    run_temperature_blind_spot_checkride,
)
from truepanel.holodeck.aegis_temperature_development_acceptance import (
    run_temperature_development_acceptance_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def _subjects():
    accepted = coverage_matrix(rehearse_recovery_paths())
    candidate = build_temperature_coverage_candidate(
        accepted, rehearse_temperature_coverage()
    )
    evidence = run_temperature_blind_spot_checkride()
    appraisal = appraise_temperature_coverage(
        accepted,
        candidate,
        evidence,
        implementation_sha256=temperature_coverage_implementation_sha256(
            run_temperature_blind_spot_checkride
        ),
    )
    return candidate, appraisal


def _confirmation(candidate, appraisal):
    request = prepare_temperature_development_acceptance(candidate, appraisal)
    return {
        "schema": CONFIRMATION_SCHEMA,
        "operator_id": OPERATOR_ID,
        "scope": SCOPE,
        "statement": REQUIRED_STATEMENT,
        "subjects": request["subjects"],
        "issued_at": "2026-10-10T04:00:00Z",
        "expires_at": "2026-10-11T04:00:00Z",
    }


def test_absent_operator_confirmation_requires_action_without_authority():
    candidate, appraisal = _subjects()
    result = evaluate_temperature_development_acceptance(
        candidate, appraisal, None, now_utc="2026-10-10T04:30:00Z"
    )
    assert result["status"] == "ACTION_REQUIRED_OPERATOR_CONFIRMATION"
    assert result["development_review_accepted"] is False
    assert result["confirmation_authenticated"] is False
    for field in (
        "accepted",
        "installed",
        "runtime_authority",
        "production_authority",
        "deployment_authority",
        "hardware_authority",
        "storage_write_authority",
        "network_authority",
        "automatic_promotion",
    ):
        assert result[field] is False


def test_exact_fixture_confirmation_advances_development_review_only():
    candidate, appraisal = _subjects()
    result = evaluate_temperature_development_acceptance(
        candidate,
        appraisal,
        _confirmation(candidate, appraisal),
        now_utc="2026-10-10T04:30:00Z",
    )
    assert result["status"] == "DEVELOPMENT_ACCEPTED_FOR_REVIEW"
    assert result["development_review_accepted"] is True
    assert result["accepted"] is False
    assert result["installed"] is False
    assert result["deployment_authority"] is False
    assert result["hardware_authority"] is False
    assert result["confirmation_authenticated"] is False


def test_wrong_operator_expiry_unknown_field_and_subject_drift_hold():
    candidate, appraisal = _subjects()
    base = _confirmation(candidate, appraisal)
    variants = []
    wrong_operator = deepcopy(base)
    wrong_operator["operator_id"] = "vega"
    variants.append(wrong_operator)
    expired = deepcopy(base)
    expired["expires_at"] = "2026-10-10T04:01:00Z"
    variants.append(expired)
    extended = deepcopy(base)
    extended["note"] = "unreviewed"
    variants.append(extended)
    substituted = deepcopy(base)
    substituted["subjects"] = dict(substituted["subjects"])
    substituted["subjects"]["appraisal_sha256"] = "0" * 64
    variants.append(substituted)

    for confirmation in variants:
        result = evaluate_temperature_development_acceptance(
            candidate, appraisal, confirmation, now_utc="2026-10-10T04:30:00Z"
        )
        assert result["status"] == "HOLD"
        assert result["development_review_accepted"] is False


def test_holodeck_acceptance_proof_has_one_fixture_acceptance_and_no_authority():
    report = run_temperature_development_acceptance_checkride()
    assert report["measurements"] == {
        "scenario_count": 11,
        "action_required_count": 1,
        "development_accepted_count": 1,
        "hold_count": 9,
        "runtime_acceptances": 0,
        "candidate_installations": 0,
        "production_authorizations": 0,
        "hardware_actions": 0,
        "runtime_writes": 0,
    }
    assert report["fixture_record"]["confirmation_authenticated"] is False


def test_preserved_development_acceptance_evidence_replays_exactly():
    preserved = json.loads(
        (
            ROOT / "docs/evidence/aegis-temperature-development-acceptance-v1.json"
        ).read_text()
    )
    assert preserved == run_temperature_development_acceptance_checkride()


def test_runtime_and_mobile_view_require_real_operator_confirmation():
    result = AegisReliabilityEngine().observe({"operator_guidance": []})
    record = result["coverage_development_acceptance"]
    assert result["coverage_summary"] == {"total": 8, "trusted": 8, "gaps": 0}
    assert record["status"] == "ACTION_REQUIRED_OPERATOR_CONFIRMATION"
    assert record["confirmation_present"] is False
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Development Acceptance" in source
    assert "JT + Vega · development review only" in source
    assert "no approval is inferred" in source
    assert "Deployment authority:" in source
    assert "@media(max-width:760px)" in source
