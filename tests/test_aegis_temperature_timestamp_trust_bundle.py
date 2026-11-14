from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.temperature_timestamp_trust_bundle import (
    pending_timestamp_trust_bundle,
)
from truepanel.holodeck.aegis_temperature_timestamp_trust_bundle import (
    run_temperature_timestamp_trust_bundle_checkride,
)


def test_pending_bundle_fails_closed():
    result = pending_timestamp_trust_bundle({"timestamp_witness_verified": True})
    assert result["status"] == "ACTION_REQUIRED_GOVERNED_TIMESTAMP_THRESHOLD"
    assert result["eligible_for_reviewer_quorum"] is False
    assert result["deployment_authority"] is False


def test_checkride_requires_distinct_governed_operators():
    proof = run_temperature_timestamp_trust_bundle_checkride()
    assert proof["measurements"]["scenario_count"] == 7
    assert proof["measurements"]["trusted_thresholds"] == 1
    assert sum(item["trusted"] for item in proof["scenarios"]) == 1
    assert proof["measurements"]["lead_samples"] == 27


def test_reliability_exposes_timestamp_trust_gate():
    result = AegisReliabilityEngine().observe({"timestamp": 0.0})[
        "coverage_timestamp_trust_bundle"
    ]
    assert result["timestamp_trust_bundle_verified"] is False
    assert result["threshold"] == 2


def test_mobile_copy_discloses_operator_threshold():
    with open("truepanel/web/static/reliability-view.js", encoding="utf-8") as stream:
        source = stream.read()
    assert "Governed Timestamp Trust" in source
    assert "one operator counts once" in source
