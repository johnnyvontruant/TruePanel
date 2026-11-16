import json
from pathlib import Path

from truepanel.aegis.reliability import AegisReliabilityEngine

ROOT = Path(__file__).resolve().parents[1]


def test_pinned_etsi_dss_receipt_is_fail_closed_and_non_operational():
    receipt = json.loads(
        (ROOT / "docs/evidence/aegis-rfc4998-etsi-dss-receipt-v1.json").read_text()
    )
    assert receipt["oracle"] == "European Commission ETSI DSS"
    assert receipt["oracle_version"] == "6.5.1"
    assert receipt["external_validations_completed"] == 2
    for field in (
        "record_parsed",
        "structural_validation_valid",
        "detached_data_found",
        "detached_data_intact",
        "timestamp_signature_valid",
        "timestamp_imprint_intact",
        "trust_anchor_reached",
        "wrong_data_rejected",
        "truncated_record_rejected",
        "wrong_trust_anchor_rejected",
    ):
        assert receipt[field] is True
    assert receipt["production_trusted"] is False
    assert receipt["deployment_authority"] is False
    assert receipt["hardware_authority"] is False


def test_ci_pins_dss_and_diffs_exact_receipt():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    pom = (ROOT / "development/interop/rfc4998-etsi-dss/pom.xml").read_text()
    source = (
        ROOT
        / "development/interop/rfc4998-etsi-dss/src/main/java/org/truepanel/aegis/Rfc4998EtsiDssOracle.java"
    ).read_text()
    assert "rfc4998-etsi-dss-oracle" in workflow
    assert "<etsi-dss.version>6.5.1</etsi-dss.version>" in pom
    assert "dss-evidence-record-asn1" in pom
    assert "diff -u" in workflow
    assert "aegis-rfc4998-etsi-dss-receipt" in workflow
    assert "setDetachedContents" in source
    assert "setTrustedCertSources" in source
    assert "wrong detached data was accepted" in source
    assert "wrong trust anchor was accepted" in source


def test_fixture_oracles_do_not_promote_active_records():
    result = AegisReliabilityEngine().observe({"timestamp": 0.0})[
        "coverage_rfc4998_interoperability"
    ]
    assert result["independent_validators_rehearsed"] == 2
    assert result["remaining_independent_oracles"] == []
    assert result["active_record_external_validation"] == "PENDING"
    assert result["external_interoperability_validation"] == "PENDING"
    assert result["eligible_for_timestamp_trust_rotation"] is False
    assert result["deployment_authority"] is False
    assert result["hardware_authority"] is False
