import json
from pathlib import Path

from truepanel.aegis import (
    AegisReliabilityEngine,
    run_flight_director_proof,
)

ROOT = Path(__file__).resolve().parents[1]


def test_flight_director_proves_end_to_end_shared_cooling_scenario():
    report = run_flight_director_proof()

    assert report["simulation"] is True
    assert report["hardware_isolated"] is True
    assert report["field_validated"] is False
    assert report["production_validated"] is False
    assert report["control_authority"] is False
    assert report["measurements"] == {
        "shared_cause_detection_sample": 19,
        "first_isolated_threshold_sample": 46,
        "detection_lead_samples": 27,
        "forecast_absolute_error_samples": 0,
        "root_cause_stability": 1.0,
        "terminal_isolated_alert_count": 2,
        "correlated_incident_count": 1,
        "alert_reduction_percent": 50,
        "repair_verification_outcome": "passed",
        "timeline_clarity": "one cause, four landmarks, raw thresholds retained",
        "topology_clarity": "13 nodes; 6 unresolved identities are labeled unknown rather than guessed",
    }
    assert len(report["incident_time_machine"]["replay"]) == 52
    assert report["safe_operating_envelope"]["uncertainty_samples"] == 2
    assert len(report["what_if_rehearsals"]) == 3
    assert all(item["hardware_isolated"] for item in report["what_if_rehearsals"])


def test_flight_director_labels_unknown_topology_and_replays_preserved_digest():
    report = run_flight_director_proof()
    nodes = report["causal_hardware_map"]["nodes"]
    unknowns = [item for item in nodes if item["certainty"] == "unknown"]
    evidence = json.loads(
        (ROOT / "docs/evidence/flight-director-shared-cooling-v1.json").read_text()
    )

    assert len(nodes) == 13
    assert len(unknowns) == 6
    assert {item["kind"] for item in unknowns} >= {"fan_channel", "drive_bay", "drive", "vdev", "pool", "workload"}
    assert evidence["report_evidence_sha256"] == report["evidence_sha256"]
    assert report["repair_verification_signature"]["outcome"] == "passed"
    assert report["recovery_flight_plan"]["affected_bay"] is None


def test_mission_control_payload_and_mobile_view_expose_flight_director():
    payload = AegisReliabilityEngine().observe({"timestamp": 1, "fans": {}, "storage": {}})
    flight = payload["flight_director"]
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()

    assert flight["scenario"] == "fan-degradation-shared-cooling-v1"
    assert flight["field_validated"] is False
    assert flight["control_authority"] is False
    for label in ("NOW", "NEXT", "WHY", "PROOF", "Incident Time Machine", "Causal Hardware Map", "HoloDeck What-If Rehearsals"):
        assert label in source
    assert "@media(max-width:760px)" in source
    assert "setInterval" not in source
