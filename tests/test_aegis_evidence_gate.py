from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from truepanel.aegis.evidence_gate import (
    builtin_lab_evidence_status,
    evaluate_evidence_gate,
    validate_field_manifest,
    wilson_interval,
)
from truepanel.holodeck.aegis_corpus import (
    builtin_corpus_path,
    load_corpus,
    run_black_box_corpus,
)


def _field_manifest() -> dict:
    cases = []
    for index in range(40):
        cases.append(
            {
                "case_id": f"field-{index:02d}",
                "expected_shared_cooling": index < 20,
                "system_profile": f"profile-{index % 2}",
                "workload_class": f"workload-{index % 4}",
                "incident_reviewed": True,
            }
        )
    return {
        "source": "operator-opt-in-field",
        "privacy": "sanitized",
        "dataset_card": {
            "collection_authority": "operator-opt-in",
            "review_state": "approved",
            "raw_identifiers_retained": False,
            "label_method": "human-reviewed-incident-outcome",
            "allowed_uses": ["aegis-calibration"],
            "retention_policy": "review annually; delete on withdrawal",
        },
        "cases": cases,
    }


def test_wilson_bounds_refuse_to_treat_perfect_small_samples_as_certainty():
    false_positive_lower, false_positive_upper = wilson_interval(0, 141)
    recall_lower, recall_upper = wilson_interval(1, 1)

    assert false_positive_lower == pytest.approx(0.0, abs=1e-12)
    assert false_positive_upper == pytest.approx(0.026522, abs=1e-6)
    assert recall_lower == pytest.approx(0.206549, abs=1e-6)
    assert recall_upper == pytest.approx(1.0)


def test_builtin_synthetic_corpus_is_held_at_lab_calibrated():
    status = builtin_lab_evidence_status()

    assert status["stage"] == "lab_calibrated"
    assert status["eligible_for_field_validation"] is False
    assert status["production_validated"] is False
    assert status["release_review_required"] is True
    assert status["measurements"]["false_positive_rate"] == 0.0
    assert status["measurements"]["false_positive_rate_wilson_upper"] == 0.026522
    assert status["measurements"]["recall_wilson_lower"] == 0.206549
    assert len(status["gaps"]) == 8
    assert status["control_authority"] is False


def test_eligible_field_evidence_still_requires_release_review():
    manifest = _field_manifest()
    report = {
        "confusion_matrix": {"true_positive": 20, "false_negative": 0},
        "negative_frame_count": 500,
        "false_positive_frame_count": 0,
    }

    assert validate_field_manifest(manifest) == ()
    status = evaluate_evidence_gate(report, manifest)
    assert status["stage"] == "field_candidate"
    assert status["eligible_for_field_validation"] is True
    assert status["production_validated"] is False
    assert status["release_review_required"] is True
    assert status["gaps"] == []
    assert status["measurements"]["false_positive_rate_wilson_upper"] == 0.007624
    assert status["measurements"]["recall_wilson_lower"] >= 0.8


def test_field_manifest_rejects_identity_retention_and_unreviewed_labels():
    manifest = _field_manifest()
    manifest["dataset_card"]["raw_identifiers_retained"] = True
    manifest["cases"][0]["incident_reviewed"] = False

    errors = validate_field_manifest(manifest)
    assert "dataset_card.raw_identifiers_retained must be false" in errors
    assert "field-00: incident_reviewed must be true" in errors


def test_field_corpus_loader_enforces_admission_before_replay(tmp_path):
    source = builtin_corpus_path()
    recording_name = "ambient-temperature-rise.jsonl"
    raw = (source / recording_name).read_bytes()
    manifest = _field_manifest()
    manifest["schema_version"] = 1
    manifest["corpus_id"] = "aegis-field-corpus-example-v1"
    manifest["cases"] = [
        {
            "case_id": "reviewed-normal-workload",
            "recording": recording_name,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "frame_count": 36,
            "expected_shared_cooling": False,
            "challenge": "reviewed-normal",
            "system_profile": "qnap-six-bay",
            "workload_class": "idle",
            "incident_reviewed": True,
        }
    ]
    manifest["corpus_sha256"] = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    (tmp_path / recording_name).write_bytes(raw)
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))

    loaded_manifest, cases = load_corpus(tmp_path)
    assert loaded_manifest["source"] == "operator-opt-in-field"
    assert len(cases[0]["frames"]) == 36

    manifest["dataset_card"]["raw_identifiers_retained"] = True
    manifest_without_digest = dict(manifest)
    manifest_without_digest.pop("corpus_sha256")
    manifest["corpus_sha256"] = hashlib.sha256(
        json.dumps(
            manifest_without_digest, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="admission failed"):
        load_corpus(tmp_path)


def test_detector_adapter_can_be_replaced_without_changing_corpus_runner():
    class NeverDetector:
        detector_id = "test-never"

        def detect(self, outlook):
            return None

    report = run_black_box_corpus(detector_factory=NeverDetector)
    assert report["detector_id"] == "test-never"
    assert report["confusion_matrix"]["false_negative"] == 1
    assert report["confusion_matrix"]["true_negative"] == 5


def test_preserved_evidence_gate_matches_runtime_contract():
    path = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "evidence"
        / "aegis-field-evidence-gate-v1.json"
    )
    assert json.loads(path.read_text(encoding="utf-8")) == builtin_lab_evidence_status()
