import json
from copy import deepcopy
from pathlib import Path

from truepanel.aegis.coverage import coverage_matrix
from truepanel.aegis.identity_coverage import (
    IDENTITY_REQUIRED_CODES,
    build_identity_coverage_candidate,
    rehearse_identity_coverage_contract,
    validate_identity_coverage_candidate,
)
from truepanel.aegis.rehearsal import rehearse_recovery_paths
from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.holodeck.aegis_identity_coverage import (
    run_identity_coverage_rehearsal,
)

ROOT = Path(__file__).resolve().parents[1]


def test_candidate_extends_but_does_not_mutate_accepted_matrix():
    accepted = coverage_matrix(rehearse_recovery_paths())
    snapshot = deepcopy(accepted)
    rehearsal = rehearse_identity_coverage_contract()

    candidate = build_identity_coverage_candidate(accepted, rehearsal)

    assert accepted == snapshot
    assert accepted["schema_version"] == 1
    assert candidate["schema_version"] == 2
    assert candidate["accepted"] is False
    assert candidate["automatic_acceptance"] is False
    assert candidate["review_required"] is True
    assert candidate["status"] == "READY_FOR_OPERATOR_REVIEW"
    assert candidate["total"] == candidate["trusted"] == 8
    assert candidate["gaps"] == 0
    assert validate_identity_coverage_candidate(candidate) == ()


def test_every_storage_recovery_requires_rehearsed_identity_continuity():
    candidate = build_identity_coverage_candidate(
        coverage_matrix(rehearse_recovery_paths()),
        rehearse_identity_coverage_contract(),
    )
    entries = {item["code"]: item for item in candidate["entries"]}

    assert tuple(candidate["identity_required_codes"]) == IDENTITY_REQUIRED_CODES
    for code in IDENTITY_REQUIRED_CODES:
        contract = entries[code]["identity_continuity"]
        assert contract["required"] is True
        assert contract["rehearsal_status"] == "passed"
        assert contract["regression_scenario"] == "aegis-stable-identity-migration"


def test_candidate_holds_when_rehearsal_is_not_proved():
    evidence = rehearse_identity_coverage_contract()
    evidence["status"] = "failed"
    candidate = build_identity_coverage_candidate(
        coverage_matrix(rehearse_recovery_paths()), evidence
    )

    assert candidate["status"] == "HOLD"
    assert len(candidate["contract_errors"]) == len(IDENTITY_REQUIRED_CODES)


def test_holodeck_replays_real_lifeline_migration_and_adversarial_cases():
    report = run_identity_coverage_rehearsal()

    assert report["result"] == "PASS"
    assert report["measurements"] == {
        "scenarios": 6,
        "trusted": 3,
        "holds": 3,
        "false_outcomes": 0,
        "migration_session_splits": 0,
        "different_drive_merges": 0,
        "identity_downgrades": 0,
        "raw_identifier_occurrences": 0,
        "additional_telemetry_reads": 0,
        "temporary_fixture_writes": 3,
        "production_writes": 0,
    }
    assert report["safety"]["disposable_directory_removed"] is True
    assert all(
        item["result"]["status"] == item["expected"] for item in report["scenarios"]
    )


def test_preserved_evidence_exactly_replays():
    expected = json.loads(
        (ROOT / "docs/evidence/aegis-identity-coverage-v1.json").read_text()
    )
    assert run_identity_coverage_rehearsal() == expected


def test_reliability_payload_keeps_accepted_and_candidate_contracts_separate():
    engine = AegisReliabilityEngine()
    observed = engine.observe({"timestamp": 1.0, "operator_guidance": []})

    assert observed["coverage_matrix"]["schema_version"] == 1
    assert observed["coverage_candidate"]["status"] == "READY_FOR_OPERATOR_REVIEW"
    assert observed["coverage_candidate"]["accepted"] is False
    assert observed["coverage_summary"] == {"total": 8, "trusted": 8, "gaps": 0}


def test_mission_control_discloses_candidate_review_boundary_on_mobile():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()

    assert "Recovery Coverage Next · Identity" in source
    assert "This candidate is not accepted" in source
    assert "Automatic acceptance" in source
    assert "ag-coverage-candidate" in source
    assert "@media(max-width:760px)" in source
    assert "setInterval" not in source
