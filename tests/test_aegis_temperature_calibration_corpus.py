from __future__ import annotations

import json
from pathlib import Path

from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.temperature_calibration_corpus import (
    pending_temperature_calibration_corpus_import,
)
from truepanel.holodeck.aegis_temperature_calibration_corpus import (
    run_temperature_calibration_corpus_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def test_live_calibration_corpus_import_waits_for_authenticated_admission():
    reliability = AegisReliabilityEngine().observe({"timestamp": 0.0})
    result = reliability["coverage_calibration_corpus_import"]
    assert result["status"] == "HOLD"
    assert result["admission_reverified"] is False
    assert result["corpus_write_performed"] is False
    assert result["append_only_commit"] is False
    assert result["case_count"] == 0
    assert result["field_validated"] is False
    assert result["candidate_installed"] is False
    assert result["deployment_authority"] is False
    assert result["hardware_authority"] is False


def test_authenticated_admission_still_requires_separate_import():
    result = pending_temperature_calibration_corpus_import(
        {"eligible_for_corpus_import": True}
    )
    assert result["status"] == "ACTION_REQUIRED_AUTHENTICATED_CORPUS_IMPORT"
    assert result["corpus_write_performed"] is False
    assert result["field_validated"] is False


def test_holodeck_append_only_import_is_preserved_and_fails_closed():
    report = run_temperature_calibration_corpus_checkride()
    assert report["measurements"] == {
        "scenario_count": 9,
        "imported_count": 1,
        "hold_count": 8,
        "committed_case_directories": 1,
        "duplicate_case_imports": 0,
        "duplicate_recording_imports": 0,
        "partial_case_directories": 0,
        "field_validations": 0,
        "candidate_acceptances": 0,
        "candidate_installations": 0,
        "deployments": 0,
        "hardware_actions": 0,
        "runtime_writes": 0,
        "private_key_inputs": 0,
        "signer_invocations_by_truepanel": 0,
    }
    preserved = json.loads(
        (ROOT / "docs/evidence/aegis-temperature-calibration-corpus-v1.json").read_text()
    )
    assert preserved == report


def test_mobile_view_exposes_append_only_import_boundary():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Append-Only Calibration Corpus" in source
    assert "Authenticated case commit" in source
    assert "duplicate case IDs and recording digests fail closed" in source
    assert "@media(max-width:760px)" in source
