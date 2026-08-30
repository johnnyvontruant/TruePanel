from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from truepanel.aegis.evidence_gate import builtin_lab_evidence_status
from truepanel.aegis.policy import DEFAULT_CORRELATION_POLICY
from truepanel.holodeck.aegis_corpus import (
    CORPUS_ID,
    builtin_corpus_path,
    load_corpus,
    run_black_box_corpus,
    validate_builtin_corpus,
)


def test_builtin_black_box_corpus_is_privacy_safe_and_content_addressed():
    manifest, cases = load_corpus()

    assert validate_builtin_corpus() == ()
    assert manifest["corpus_id"] == CORPUS_ID
    assert manifest["privacy"] == "sanitized"
    assert manifest["source"] == "deterministic-synthetic"
    assert len(cases) == 6
    assert sum(len(case["frames"]) for case in cases) == 193


def test_black_box_corpus_proves_detection_and_adversarial_rejection():
    report = run_black_box_corpus()

    assert report["confusion_matrix"] == {
        "true_positive": 1,
        "false_positive": 0,
        "true_negative": 5,
        "false_negative": 0,
    }
    assert report["negative_frame_false_positive_rate"] == 0.0
    assert report["precision"] == report["recall"] == report["specificity"] == 1.0
    assert all(result["passed"] for result in report["results"])
    positive = report["results"][0]
    assert positive["first_policy_match_index"] == 19
    assert positive["lead_samples"] == 27
    assert positive["root_cause_stability"] == 1.0
    assert positive["confidence_mean"] == 0.94
    assert positive["confidence_pstdev"] == 0.057


def test_preserved_black_box_corpus_evidence_matches_replay():
    evidence = (
        Path(__file__).resolve().parents[1] / "docs" / "evidence" / f"{CORPUS_ID}.json"
    )
    assert json.loads(evidence.read_text(encoding="utf-8")) == run_black_box_corpus()


def test_correlation_policy_requires_the_versioned_corpus():
    description = DEFAULT_CORRELATION_POLICY.describe()

    assert description["verification_scenarios"] == [CORPUS_ID]
    assert description["calibration"] == {
        "corpus_id": CORPUS_ID,
        "scope": "deterministic_fixture",
        "production_validated": False,
        "evidence": "docs/evidence/aegis-black-box-corpus-v1.json",
        "evidence_gate": builtin_lab_evidence_status(),
        "field_workflow": {
            "workflow_id": "aegis-field-corpus-workflow-v1",
            "state": "not_started",
            "stages": ["consent", "intake", "review", "freeze", "assess"],
            "next_action": "initialize an opt-in, sanitized field corpus",
            "live_capture": False,
            "control_authority": False,
        },
    }


def test_corpus_rejects_tampering_before_replay(tmp_path):
    source = builtin_corpus_path()
    target = tmp_path / "corpus"
    target.mkdir()
    for path in source.iterdir():
        (target / path.name).write_bytes(path.read_bytes())
    recording = target / "fan-bearing-degradation.jsonl"
    recording.write_bytes(recording.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="recording digest mismatch"):
        load_corpus(target)


def test_manifest_digest_is_stable():
    manifest = json.loads((builtin_corpus_path() / "manifest.json").read_text())
    expected = manifest.pop("corpus_sha256")
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(encoded).hexdigest() == expected
