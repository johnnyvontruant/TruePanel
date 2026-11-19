import copy
import json
from pathlib import Path

from truepanel.aegis.rfc4998_authenticated_custody import (
    SCHEMA as AUTHENTICATED_SCHEMA,
)
from truepanel.aegis.rfc4998_authenticated_custody import STATUS_AUTHENTICATED
from truepanel.aegis.rfc4998_timestamped_custody import (
    STATUS_HOLD,
    STATUS_TIMESTAMP_REQUIRED,
    STATUS_TIMESTAMPED,
    evaluate_timestamped_custody,
)
from truepanel.holodeck.aegis_rfc4998_timestamped_custody import (
    run_rfc4998_timestamped_custody_checkride,
)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence"


def _authenticated():
    return {
        "schema": AUTHENTICATED_SCHEMA,
        "status": STATUS_AUTHENTICATED,
        "record_id": "record-1",
        "custody_id": "custody-1",
        "custodian_id": "aegis-preservation-custodian",
        "record_sha256": "a" * 64,
        "issued_at": "2026-11-18T04:00:00Z",
        "expires_at": "2026-11-18T04:15:00Z",
        "custodian_signature_verified": True,
        "dual_oracle_receipt_verified": True,
        "production_trusted": False,
        "runtime_authority": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "network_authority": False,
        "storage_authority": False,
    }


def _verified(*_):
    return {
        "verified": True,
        "profile": "RFC3161",
        "policy_oid": "1.3.6.1.4.1.55555.1",
        "gen_time_utc": "2026-11-18T04:05:00Z",
        "hash_algorithm": "sha256",
        "errors": [],
    }


def test_exact_signature_countersignature_is_time_rehearsed_only():
    result = evaluate_timestamped_custody(
        _authenticated(), "signature", b"timestamp", _verified
    )
    assert result["status"] == STATUS_TIMESTAMPED
    assert result["timestamp_profile"] == "RFC3161"
    assert result["timestamp_token_sha256"]
    assert result["eligible_for_production_trust"] is False
    assert result["production_trusted"] is False
    assert result["runtime_authority"] is False
    assert result["deployment_authority"] is False
    assert result["hardware_authority"] is False


def test_missing_out_of_window_and_authority_paths_fail_closed():
    authenticated = _authenticated()
    missing = evaluate_timestamped_custody(
        authenticated, "signature", None, _verified
    )
    assert missing["status"] == STATUS_TIMESTAMP_REQUIRED

    malformed = evaluate_timestamped_custody(
        authenticated, "signature", "not-bytes", _verified
    )
    assert malformed["status"] == STATUS_HOLD
    assert "CustodyTimestampTokenInvalid" in malformed["errors"]

    def late(*_):
        result = _verified()
        result["gen_time_utc"] = "2026-11-18T04:15:01Z"
        return result

    timestamp_late = evaluate_timestamped_custody(
        authenticated, "signature", b"timestamp", late
    )
    assert timestamp_late["status"] == STATUS_HOLD
    assert "CustodyTimestampAfterValidity" in timestamp_late["errors"]

    escalated = copy.deepcopy(authenticated)
    escalated["network_authority"] = True
    authority = evaluate_timestamped_custody(
        escalated, "signature", b"timestamp", _verified
    )
    assert authority["status"] == STATUS_HOLD
    assert "AuthenticatedCustodyAuthorityEscalation" in authority["errors"]


def test_real_rfc3161_checkride_matches_reviewed_evidence():
    result = run_rfc4998_timestamped_custody_checkride(ROOT)
    assert result == json.loads(
        (EVIDENCE / "aegis-rfc4998-timestamped-custody-checkride-v1.json").read_text()
    )
    assert result["measurements"]["scenario_count"] == 10
    assert result["measurements"]["rfc3161_countersignatures_verified"] == 1
    assert result["measurements"]["hold_or_action_required_count"] == 9
    assert result["measurements"]["out_of_window_timestamp_acceptances"] == 0
    assert result["measurements"]["coverage_gaps"] == 0
    assert result["measurements"]["lead_samples"] == 27


def test_ci_and_mobile_view_expose_custody_time_contract():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "rfc4998-timestamped-custody" in workflow
    assert "needs: rfc4998-authenticated-custody" in workflow
    assert "aegis-rfc4998-timestamped-custody-checkride" in workflow
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "RFC 4998 Custody Time" in source
    assert "RFC 3161 countersignature" in source
    assert "Active-record custody time" in source
