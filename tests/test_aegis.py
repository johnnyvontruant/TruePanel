from __future__ import annotations

import copy
import http.client
import json
import threading
from pathlib import Path

from truepanel.aegis import (
    AegisReliabilityEngine,
    correlate_incident,
    coverage_matrix,
    rehearse_recovery_paths,
    validate_correlation_policy,
    validate_recovery_coverage,
)
from truepanel.guidance import guidance_for_snapshot
from truepanel.guidance.catalog import guidance_codes
from truepanel.guidance.recovery import recovery_contract
from truepanel.guidance.sessions import RecoverySessionStore
from truepanel.holodeck.aegis_calibration import run_correlation_calibration
from truepanel.holodeck.aegis_lab import run_shared_cooling_experiment
from truepanel.web import pathfinder_server


def _card(code, *, evidence=None, title=None):
    card = {
        "code": code,
        "title": title or code,
        "severity": "warning",
        "summary": f"{code} detected",
        "immediate_actions": [
            {"title": "Stabilize", "detail": "Reduce avoidable load and inspect passive evidence."}
        ],
        "diagnosis": [{"title": "Inspect", "detail": "Review evidence."}],
        "remediation": [{"title": "Repair", "detail": "Correct the verified cause."}],
        "verification": [{"title": "Verify", "detail": "Recheck telemetry."}],
        "runtime": {
            "phase": "diagnose",
            "evidence": dict(evidence or {}),
            "action_gate": {
                "safe_checks": True,
                "physical_service_ready": False,
                "destructive_actions_ready": False,
                "blocked_by": [],
            },
        },
    }
    card["recovery"] = recovery_contract(card)
    return card


def test_recovery_coverage_contract_is_complete_and_ci_enforceable():
    rehearsals = rehearse_recovery_paths()
    matrix = coverage_matrix(rehearsals)

    assert validate_recovery_coverage() == ()
    assert validate_correlation_policy() == ()
    assert {item["code"] for item in matrix["entries"]} == set(guidance_codes())
    assert matrix["total"] == 8
    assert matrix["trusted"] == matrix["total"]
    assert matrix["gaps"] == 0
    assert all(item["coverage_state"] == "TRUSTED" for item in matrix["entries"])
    assert all(item["verification"]["machine_verifiable"] for item in matrix["entries"])
    assert all(item["regression_scenarios"] for item in matrix["entries"])


def test_every_recovery_path_is_rehearsed_without_production_mutation():
    evidence = rehearse_recovery_paths()

    assert set(evidence) == set(guidance_codes())
    assert all(item["status"] == "passed" for item in evidence.values())
    assert all(item["simulation"] is True for item in evidence.values())
    assert all(item["production_mutation"] is False for item in evidence.values())
    assert all(len(item["evidence_sha256"]) == 64 for item in evidence.values())


def test_shared_cooling_incident_consolidates_alerts_and_keeps_evidence():
    cards = [
        _card("cooling.fan_stall", evidence={"fan_channel": 1, "current_rpm": 0}),
        _card(
            "thermal.high_temperature",
            evidence={"current_temperature_c": 74, "recovery_threshold_c": 68},
        ),
    ]
    outlook = {
        "active_signals": ["fan.rpm", "drive.temperature_c"],
        "metrics": {
            "fan.rpm": {"state": "FAULT", "value": 0, "baseline_mean": 1500, "confidence": 1},
            "drive.temperature_c": {"state": "WATCH", "value": 42, "baseline_mean": 36, "confidence": 1},
        },
        "correlations": [
            {"key": "chassis.airflow", "state": "DEVELOPING"},
        ],
    }

    incident = correlate_incident(cards, outlook)

    assert incident is not None
    assert incident["likely_cause"] == "Shared chassis cooling degradation"
    assert incident["consolidated_alert_count"] == 1
    assert incident["suppressed_duplicate_count"] == 1
    assert incident["contributing_alerts"] == [
        "cooling.fan_stall",
        "thermal.high_temperature",
    ]
    assert incident["confidence"] >= 0.8
    assert len(incident["supporting_signals"]) == 4
    assert incident["read_only"] is True
    assert incident["control_authority"] is False
    assert incident["presentation"] == {
        "group_by": ["physical_domain", "probable_cause"],
        "inhibited_alerts": ["thermal.high_temperature"],
        "raw_alerts_retained": True,
    }


def test_declarative_policy_requires_fan_delivery_evidence():
    thermal_only = {
        "active_signals": ["drive.temperature_c", "cpu.temperature_c"],
        "metrics": {
            "drive.temperature_c": {"state": "WATCH", "value": 41},
            "cpu.temperature_c": {"state": "WATCH", "value": 62},
        },
        "correlations": [],
    }

    assert correlate_incident([], thermal_only) is None


def test_correlation_policy_is_replaceable_without_changing_composition():
    class NeverCorrelatePolicy:
        def evaluate(self, cards, outlook):
            return None

        def describe(self):
            return {"policy_id": "test-never", "replaceable": True}

        def validate(self, *, known_alerts=()):
            return ()

    engine = AegisReliabilityEngine(correlation_policy=NeverCorrelatePolicy())
    result = engine.observe(
        {
            "timestamp": 1,
            "operator_guidance": [],
            "fans": {"channels": []},
            "storage": {},
            "network": [],
        }
    )

    assert result["active_incident"] is None
    assert result["correlation_policy"] == {
        "policy_id": "test-never",
        "replaceable": True,
    }


def test_holodeck_correlation_calibration_rejects_adversarial_negatives():
    report = run_correlation_calibration()

    assert report["simulation"] is True
    assert report["hardware_isolated"] is True
    assert report["production_mutation"] is False
    assert report["corpus_size"] == 4
    assert report["confusion_matrix"] == {
        "true_positive": 1,
        "false_positive": 0,
        "true_negative": 3,
        "false_negative": 0,
    }
    assert report["precision"] == 1.0
    assert report["recall"] == 1.0
    assert report["specificity"] == 1.0
    assert report["legacy_false_positive_scenarios"] >= 1
    assert all(item["passed"] for item in report["results"])
    shared = report["results"][0]
    assert shared["first_policy_match_index"] == 19
    assert shared["first_isolated_threshold_index"] == 46
    assert shared["lead_samples"] == 27
    assert len(report["evidence_sha256"]) == 64


def test_preserved_calibration_evidence_matches_the_deterministic_runner():
    evidence_path = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "evidence"
        / "aegis-correlation-calibration-v1.json"
    )

    assert json.loads(evidence_path.read_text(encoding="utf-8")) == (
        run_correlation_calibration()
    )


def test_holodeck_shared_cooling_proof_is_earlier_and_clearer():
    report = run_shared_cooling_experiment()

    assert report["simulation"] is True
    assert report["hardware_isolated"] is True
    assert report["production_mutation"] is False
    assert report["identified_earlier"] is True
    assert report["lead_samples"] == 27
    assert report["terminal_independent_alert_count"] == 2
    assert report["aegis_incident_count"] == 1
    assert report["alert_reduction_percent"] == 50
    assert report["verification_rehearsal"]["status"] == "passed"
    assert report["black_box_evidence"]["frame_count"] == 2
    assert all(
        frame["privacy"] == "sanitized"
        for frame in report["black_box_evidence"]["frames"]
    )
    assert len(report["evidence_sha256"]) == 64


def test_reliability_engine_keeps_nominal_payload_read_only():
    engine = AegisReliabilityEngine()
    payload = {
        "timestamp": 1,
        "operator_guidance": [],
        "fans": {
            "channels": [
                {"number": 1, "monitored": True, "rpm": 1500, "pwm": 180},
                {"number": 2, "monitored": True, "rpm": 1480, "pwm": 180},
            ],
            "control": {"thermal_hottest_temperature_c": 51},
        },
        "storage": {"temperatures": [{"temperature_c": 36}]},
        "network": [],
    }
    before = copy.deepcopy(payload)

    result = engine.observe(payload)

    assert payload == before
    assert result["read_only"] is True
    assert result["production_mutation"] is False
    assert result["active_incident"] is None
    assert result["coverage_summary"] == {"total": 8, "trusted": 8, "gaps": 0}
    assert result["correlation_policy"]["replaceable"] is True
    assert result["correlation_policy"]["provenance"]["license"] == "Apache-2.0"



def test_reliability_sampling_is_independent_of_duplicate_browser_reads():
    engine = AegisReliabilityEngine(sample_interval_seconds=5.0)
    payload = {
        "timestamp": 100.0,
        "operator_guidance": [],
        "fans": {
            "channels": [
                {"number": 1, "monitored": True, "rpm": 1500, "pwm": 180},
            ],
            "control": {"thermal_hottest_temperature_c": 51},
        },
        "storage": {
            "temperatures": [{"temperature_c": 36}],
            "smart": [{"reallocated": 0}],
        },
        "network": [],
    }

    first = engine.observe(payload)
    duplicate_payload = copy.deepcopy(payload)
    duplicate_payload["timestamp"] = 101.0
    duplicate_payload["fans"]["channels"][0]["rpm"] = 100
    duplicate_payload["storage"]["smart"][0]["reallocated"] = 7
    duplicate = engine.observe(duplicate_payload)

    assert first["sampling"]["fresh_sample"] is True
    assert duplicate["sampling"]["fresh_sample"] is False
    assert duplicate["oracle"] == first["oracle"]
    assert duplicate["sampling"]["sampled_at"] == 100.0
    assert duplicate["sampling"]["request_count"] == 2

    next_payload = copy.deepcopy(duplicate_payload)
    next_payload["timestamp"] = 105.0
    sampled = engine.observe(next_payload)

    assert sampled["sampling"]["fresh_sample"] is True
    assert sampled["sampling"]["sampled_at"] == 105.0
    assert sampled["oracle"]["metrics"]["fan.rpm"]["value"] == 100.0
    assert sampled["oracle"]["metrics"]["drive.smart_reallocated"]["value"] == 7.0


def test_verified_alert_correlation_is_immediate_between_oracle_samples():
    engine = AegisReliabilityEngine(sample_interval_seconds=5.0)
    baseline = {
        "timestamp": 100.0,
        "operator_guidance": [],
        "fans": {
            "channels": [
                {"number": 1, "monitored": True, "rpm": 1500, "pwm": 180},
            ],
            "control": {},
        },
        "storage": {},
        "network": [],
    }
    first = engine.observe(baseline)

    fault = copy.deepcopy(baseline)
    fault["timestamp"] = 101.0
    fault["operator_guidance"] = [
        _card(
            "cooling.fan_stall",
            evidence={"fan_channel": 1, "current_rpm": 0},
        )
    ]
    result = engine.observe(fault)

    assert result["sampling"]["fresh_sample"] is False
    assert result["oracle"] == first["oracle"]
    assert result["state"] == "INCIDENT"
    assert result["active_incident"]["contributing_alerts"] == [
        "cooling.fan_stall"
    ]



def test_cataloged_thermal_and_stale_faults_have_live_detection_adapters():
    thermal = guidance_for_snapshot(
        {
            "fans": {
                "control": {
                    "thermal_telemetry_valid": True,
                    "thermal_recommended_profile": "afterburners",
                    "thermal_hottest_temperature_c": 74,
                }
            }
        }
    )
    stale = guidance_for_snapshot(
        {
            "fans": {
                "control": {
                    "thermal_telemetry_valid": False,
                    "thermal_control_reason": "Thermal telemetry is stale.",
                    "thermal_control_state": "safe_automatic",
                    "control_authority": "automatic",
                    "safety_hold": False,
                }
            }
        }
    )

    assert [item["code"] for item in thermal] == ["thermal.high_temperature"]
    assert thermal[0]["runtime"]["evidence"]["current_temperature_c"] == 74
    assert [item["code"] for item in stale] == ["telemetry.stale"]
    assert stale[0]["runtime"]["evidence"]["missing_domains"] == ["thermal"]


class _SnapshotService:
    def status(self):
        return {
            "timestamp": 1,
            "operator_guidance": [
                _card(
                    "network.link_down",
                    evidence={"interface": "eth0", "link_up": False, "address": None},
                )
            ],
            "health": {"subsystems": {"network": {"state": "DEGRADED"}}},
            "storage": {},
            "fans": {},
            "network": [],
        }


class _BayMirror:
    def snapshot(self):
        return {"available": True, "bays": [], "count": 0}


def _request(server, path):
    host, port = server.server_address
    connection = http.client.HTTPConnection(host, port, timeout=3)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, response.getheader("Content-Type"), response.read()
    finally:
        connection.close()


def test_mission_control_publishes_reliability_payload_and_mobile_asset(tmp_path):
    server = pathfinder_server.MissionControlServer(
        ("127.0.0.1", 0),
        snapshot_service=_SnapshotService(),
        recovery_session_store=RecoverySessionStore(None),
        bay_mirror_provider=_BayMirror(),
        lifeline_identify_service=object(),
        config_path=tmp_path / "truepanel.yaml",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, content_type, raw = _request(server, "/api/v1/status")
        assert status == 200
        assert content_type.startswith("application/json")
        payload = json.loads(raw)
        reliability = payload["reliability"]
        assert reliability["project"] == "AEGIS"
        assert reliability["active_incident"]["likely_cause"] == "network.link_down"

        status, _, dashboard = _request(server, "/")
        assert status == 200
        assert b'/reliability-view.js' in dashboard

        status, content_type, script = _request(server, "/reliability-view.js")
        source = script.decode("utf-8")
        assert status == 200
        assert content_type.startswith("application/javascript")
        assert 'view.id="aegisReliabilityView"' in source
        assert "@media(max-width:760px)" in source
        assert "Safest next action" in source
        assert "Supporting signals" in source
        assert "Recovery Coverage Matrix" in source
        assert "correlation_policy" in source
        assert "raw alerts" in source
        assert 'window.addEventListener("truepanel:status"' in source
        assert "window.setInterval" not in source
        dashboard_source = dashboard.decode("utf-8")
        assert "new CustomEvent(" in dashboard_source
        assert '"truepanel:status"' in dashboard_source
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
