import json
from pathlib import Path

import pytest

from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.rfc4998_active_receipt import (
    STATUS_REHEARSED,
    ActiveReceiptError,
    join_active_record_receipts,
)
from truepanel.holodeck.aegis_rfc4998_active_receipt import (
    run_rfc4998_active_receipt_checkride,
)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence"


def _inputs():
    manifest = json.loads(
        (EVIDENCE / "aegis-rfc4998-active-record-manifest-v1.json").read_text()
    )
    receipts = [
        json.loads(
            (EVIDENCE / "aegis-rfc4998-bouncycastle-receipt-v1.json").read_text()
        ),
        json.loads((EVIDENCE / "aegis-rfc4998-etsi-dss-receipt-v1.json").read_text()),
    ]
    return manifest, receipts


def test_exact_dual_oracle_receipts_bind_one_record_without_authority():
    manifest, receipts = _inputs()
    result = join_active_record_receipts(manifest, receipts)
    assert result["active_record_external_validation"] == STATUS_REHEARSED
    assert len(result["oracle_receipts"]) == 2
    assert result["subject_digests_agree"] is True
    assert result["eligible_for_production_trust"] is False
    assert result["production_trusted"] is False
    assert result["deployment_authority"] is False
    assert result["hardware_authority"] is False


def test_receipt_join_fails_closed_for_missing_or_mismatched_evidence():
    manifest, receipts = _inputs()
    with pytest.raises(ActiveReceiptError, match="RequiredOracleMissing"):
        join_active_record_receipts(manifest, receipts[:1])
    receipts[1]["fixture_sha256"] = "0" * 64
    with pytest.raises(ActiveReceiptError, match="RecordDigestMismatch"):
        join_active_record_receipts(manifest, receipts)


def test_holodeck_rehearses_positive_and_adversarial_join_paths():
    result = run_rfc4998_active_receipt_checkride(ROOT)
    assert result == json.loads(
        (EVIDENCE / "aegis-rfc4998-active-record-checkride-v1.json").read_text()
    )
    assert result["measurements"] == {
        "scenario_count": 8,
        "trusted_rehearsals": 1,
        "hold_count": 7,
        "oracle_receipts_joined": 2,
        "record_digest_mismatch_acceptances": 0,
        "detached_digest_mismatch_acceptances": 0,
        "failed_verdict_acceptances": 0,
        "authority_escalations": 0,
        "coverage_total": 8,
        "coverage_trusted": 8,
        "coverage_gaps": 0,
        "shared_cooling_first_match_sample": 19,
        "isolated_threshold_first_match_sample": 46,
        "lead_samples": 27,
        "deployments": 0,
        "hardware_actions": 0,
        "runtime_writes": 0,
    }


def test_mission_control_exposes_rehearsed_contract_but_active_record_stays_pending():
    result = AegisReliabilityEngine().observe({"timestamp": 0.0})[
        "coverage_rfc4998_interoperability"
    ]
    assert result["per_record_receipt_contract"] == "DUAL_ORACLE_REHEARSAL_PASSED"
    assert result["active_record_external_validation"] == "PENDING"
    assert result["eligible_for_timestamp_trust_rotation"] is False


def test_ci_joins_same_run_oracle_artifacts_and_preserves_receipt():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "rfc4998-active-record-receipt" in workflow
    assert "needs:" in workflow
    assert "actions/download-artifact@v4" in workflow
    assert "aegis-rfc4998-active-record-receipt" in workflow
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Per-record receipt contract" in source
