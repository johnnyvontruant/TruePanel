from __future__ import annotations

import json
import shutil
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from truepanel.aegis.assurance import (
    evaluate_airworthiness,
    load_assurance_envelope,
    validate_repository_evidence,
)
from truepanel.aegis.coverage import coverage_matrix
from truepanel.aegis.policy import DEFAULT_CORRELATION_POLICY
from truepanel.aegis.rehearsal import rehearse_recovery_paths
from truepanel.holodeck.aegis_assurance import run_airworthiness_rehearsal

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC).timestamp()


def _evaluate(**overrides):
    arguments = {
        "payload": {"system": {"truenas_version": "25.10.5"}},
        "coverage_matrix": coverage_matrix(rehearse_recovery_paths()),
        "correlation_policy": DEFAULT_CORRELATION_POLICY.describe(),
        "now": NOW,
    }
    arguments.update(overrides)
    return evaluate_airworthiness(**arguments)


def test_accepted_contract_is_current_and_has_no_authority():
    result = _evaluate()

    assert result["status"] == "CURRENT"
    assert result["reason"] == "InsideValidatedEnvelope"
    assert result["platform_scope"] == "TrueNAS SCALE 25.10.5"
    assert len(result["subjects"]) == 5
    assert all(item["status"] == "MATCH" for item in result["subjects"])
    assert result["raw_alerts_retained"] is True
    assert result["recovery_guidance_visible"] is True
    assert result["production_mutation"] is False
    assert result["control_authority"] is False


def test_missing_platform_fact_is_review_not_false_validation():
    result = _evaluate(payload={"system": {}})

    assert result["status"] == "REVIEW"
    assert result["reason"] == "PlatformVersionUnobserved"
    platform = next(
        item
        for item in result["conditions"]
        if item["type"] == "PlatformVersionMatches"
    )
    assert platform["status"] == "Unknown"


def test_every_known_drift_class_fails_closed(tmp_path):
    matrix = coverage_matrix(rehearse_recovery_paths())
    incomplete = deepcopy(matrix)
    incomplete["gaps"] = 1
    assert _evaluate(coverage_matrix=incomplete)["status"] == "HOLD"
    assert _evaluate(correlation_policy={"policy_id": "changed"})["status"] == "HOLD"
    assert (
        _evaluate(payload={"system": {"truenas_version": "26.0.0"}})["status"] == "HOLD"
    )

    package_root = tmp_path / "truepanel"
    source_root = Path(__file__).parents[1] / "truepanel"
    for relative in (
        "aegis/policy.py",
        "aegis/coverage.py",
        "aegis/passive_runtime.py",
        "aegis/passive_websocket.py",
        "guidance/recovery.py",
    ):
        destination = package_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_root / relative, destination)
    (package_root / "aegis/policy.py").write_text("tampered", encoding="utf-8")
    assert _evaluate(package_root=package_root)["status"] == "HOLD"


def test_expiration_and_clock_rollback_hold():
    assert (
        _evaluate(now=datetime(2027, 1, 1, tzinfo=UTC).timestamp())["reason"]
        == "EnvelopeExpired"
    )
    assert (
        _evaluate(now=datetime(2026, 1, 1, tzinfo=UTC).timestamp())["reason"]
        == "ClockPredatesEnvelope"
    )


def test_malformed_envelope_holds_without_leaking_parser_details():
    result = _evaluate(envelope={"schema_version": 1})

    assert result["status"] == "HOLD"
    assert result["reason"] == "EnvelopeUnavailable"
    assert result["control_authority"] is False


def test_explicit_empty_envelope_fails_closed():
    result = _evaluate(envelope={})

    assert result["status"] == "HOLD"
    assert result["raw_alerts_retained"] is True
    assert result["recovery_guidance_visible"] is True
    assert result["production_mutation"] is False
    assert result["control_authority"] is False


def test_repository_evidence_subjects_match():
    root = Path(__file__).parents[1]
    assert validate_repository_evidence(root) == ()


def test_packaged_envelope_is_json_and_rehearsal_covers_all_paths():
    envelope = load_assurance_envelope()
    json.dumps(envelope, allow_nan=False)
    report = run_airworthiness_rehearsal()

    assert report["simulation"] is True
    assert report["hardware_isolated"] is True
    assert report["production_mutation"] is False
    assert report["control_authority"] is False
    assert report["status_counts"] == {"CURRENT": 1, "REVIEW": 1, "HOLD": 6}
    assert all(
        item["status"] == "HOLD"
        for item in report["scenarios"]
        if item["scenario"] not in {"accepted-envelope", "platform-unobserved"}
    )
    assert len(report["evidence_sha256"]) == 64
