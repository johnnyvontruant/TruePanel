import copy
import json
from pathlib import Path

from truepanel.aegis.rfc4998_authenticated_custody import (
    CUSTODY_SCHEMA,
    KEY_ID,
    NAMESPACE,
    STATUS_AUTHENTICATED,
    STATUS_HOLD,
    build_custody_statement,
    evaluate_authenticated_custody,
)
from truepanel.holodeck.aegis_rfc4998_authenticated_custody import (
    run_rfc4998_authenticated_custody_checkride,
)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence"
NOW = "2026-11-17T04:05:00Z"


def _inputs():
    manifest = json.loads(
        (EVIDENCE / "aegis-rfc4998-active-record-manifest-v1.json").read_text()
    )
    receipt = json.loads(
        (EVIDENCE / "aegis-rfc4998-active-record-receipt-v1.json").read_text()
    )
    custody = {
        "schema": CUSTODY_SCHEMA,
        "custody_id": "custody-holodeck-rfc4998-0001",
        "custodian_id": KEY_ID,
        "key_id": KEY_ID,
        "namespace": NAMESPACE,
        "record_id": manifest["record_id"],
        "source": "HOLODECK_BLACK_BOX_EXPORT_REHEARSAL",
        "transfer_mode": "READ_ONLY",
        "sequence": 1,
        "previous_custody_sha256": None,
        "clock_evidence": "DETERMINISTIC_SIMULATION_CLOCK",
        "subjects": manifest["subjects"],
        "issued_at": "2026-11-17T04:00:00Z",
        "expires_at": "2026-11-17T04:15:00Z",
        "production_trusted": False,
        "runtime_authority": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "network_authority": False,
        "storage_authority": False,
    }
    return manifest, receipt, custody


def test_exact_statement_and_signature_authenticate_only_rehearsed_custody():
    manifest, receipt, custody = _inputs()
    statement = build_custody_statement(
        manifest, receipt, custody, now_utc=NOW
    )
    calls = []

    def verifier(key_id, payload, signature):
        calls.append((key_id, payload, signature))
        return True

    result = evaluate_authenticated_custody(
        manifest, receipt, custody, "fixture-signature", verifier, now_utc=NOW
    )
    assert calls == [(KEY_ID, statement, "fixture-signature")]
    assert result["status"] == STATUS_AUTHENTICATED
    assert result["custodian_signature_verified"] is True
    assert result["active_runtime_record_validation"] == "PENDING"
    assert result["eligible_for_production_trust"] is False
    assert result["production_trusted"] is False
    assert result["deployment_authority"] is False
    assert result["hardware_authority"] is False


def test_changed_receipt_expiry_and_authority_fail_closed():
    manifest, receipt, custody = _inputs()
    changed = copy.deepcopy(receipt)
    changed["oracle_receipts"][0]["canonical_receipt_sha256"] = "0" * 64
    assert evaluate_authenticated_custody(
        manifest, changed, custody, "old", lambda *_: False, now_utc=NOW
    )["status"] == STATUS_HOLD

    expired = copy.deepcopy(custody)
    expired["issued_at"] = "2026-11-17T03:00:00Z"
    expired["expires_at"] = "2026-11-17T03:15:00Z"
    result = evaluate_authenticated_custody(
        manifest, receipt, expired, "old", lambda *_: True, now_utc=NOW
    )
    assert result["status"] == STATUS_HOLD
    assert "CustodyExpired" in result["errors"]

    authority = copy.deepcopy(custody)
    authority["hardware_authority"] = True
    result = evaluate_authenticated_custody(
        manifest, receipt, authority, "old", lambda *_: True, now_utc=NOW
    )
    assert result["status"] == STATUS_HOLD
    assert "CustodyAuthorityEscalation" in result["errors"]


def test_real_sshsig_holodeck_checkride_matches_reviewed_evidence():
    result = run_rfc4998_authenticated_custody_checkride(ROOT)
    assert result == json.loads(
        (EVIDENCE / "aegis-rfc4998-authenticated-custody-checkride-v1.json").read_text()
    )
    assert result["measurements"]["scenario_count"] == 10
    assert result["measurements"]["authenticated_custody_rehearsals"] == 1
    assert result["measurements"]["hold_or_action_required_count"] == 9
    assert result["measurements"]["coverage_gaps"] == 0
    assert result["measurements"]["lead_samples"] == 27
    assert result["measurements"]["deployments"] == 0


def test_ci_consumes_same_run_receipt_and_preserves_custody_checkride():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "rfc4998-authenticated-custody" in workflow
    assert "needs: rfc4998-active-record-receipt" in workflow
    assert "aegis-rfc4998-active-record-receipt" in workflow
    assert "aegis-rfc4998-authenticated-custody-checkride" in workflow
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Authenticated custody contract" in source
    assert "Active record custody" in source
