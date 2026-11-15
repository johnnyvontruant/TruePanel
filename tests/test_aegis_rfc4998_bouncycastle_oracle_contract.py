import base64
import hashlib
import json
from pathlib import Path

from truepanel.aegis.reliability import AegisReliabilityEngine

ROOT = Path(__file__).resolve().parents[1]


def test_preserved_fixture_is_content_addressed_and_contains_no_private_key():
    fixture = json.loads(
        (ROOT / "docs/evidence/aegis-rfc4998-bouncycastle-fixture-v1.json").read_text()
    )
    record = base64.b64decode(fixture["evidence_record_der_base64"])
    detached = base64.b64decode(fixture["detached_data_base64"])
    assert hashlib.sha256(record).hexdigest() == fixture["evidence_record_sha256"]
    assert hashlib.sha512(detached).hexdigest() == fixture["detached_data_sha512"]
    assert fixture["private_keys_retained"] is False
    assert "PRIVATE KEY" not in json.dumps(fixture)
    assert fixture["production_trusted"] is False


def test_pinned_bouncycastle_receipt_is_fail_closed_and_non_operational():
    receipt = json.loads(
        (ROOT / "docs/evidence/aegis-rfc4998-bouncycastle-receipt-v1.json").read_text()
    )
    assert receipt["oracle"] == "Bouncy Castle"
    assert receipt["oracle_version"] == "1.86"
    assert receipt["external_validations_completed"] == 1
    assert receipt["record_parsed"] is True
    assert receipt["der_round_trip_exact"] is True
    assert receipt["detached_data_present"] is True
    assert receipt["timestamp_signature_valid"] is True
    assert receipt["pkix_chain_valid_at_timestamp"] is True
    assert receipt["wrong_data_rejected"] is True
    assert receipt["truncated_record_rejected"] is True
    assert receipt["wrong_trust_anchor_rejected"] is True
    assert receipt["production_trusted"] is False
    assert receipt["deployment_authority"] is False
    assert receipt["hardware_authority"] is False


def test_ci_requires_exact_independent_oracle_receipt():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "rfc4998-bouncycastle-oracle" in workflow
    assert (
        "<bouncycastle.version>1.86</bouncycastle.version>"
        in (ROOT / "development/interop/rfc4998-bouncycastle/pom.xml").read_text()
    )
    assert "diff -u" in workflow
    assert "aegis-rfc4998-bouncycastle-receipt" in workflow


def test_mission_control_distinguishes_fixture_proof_from_active_record():
    result = AegisReliabilityEngine().observe({"timestamp": 0.0})[
        "coverage_rfc4998_interoperability"
    ]
    assert result["independent_oracle_fixture_validation"] == (
        "BOUNCY_CASTLE_1.86_PASSED"
    )
    assert result["active_record_external_validation"] == "PENDING"
    assert result["independent_validators_rehearsed"] == 1
    assert result["eligible_for_timestamp_trust_rotation"] is False

    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Independent fixture oracle" in source
    assert "Active record" in source
    assert "never an untested active record" in source
