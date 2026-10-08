from __future__ import annotations

import json
from pathlib import Path

from truepanel.aegis import (
    AegisReliabilityEngine,
    build_temperature_coverage_candidate,
    correlate_incident,
    coverage_matrix,
    rehearse_recovery_paths,
    rehearse_temperature_coverage,
    temperature_guidance_for_snapshot,
    validate_temperature_coverage_candidate,
    verify_temperature_coverage,
)
from truepanel.guidance import guidance_for_snapshot
from truepanel.guidance.recovery import recovery_contract
from truepanel.holodeck.aegis_temperature_blind_spot import (
    run_temperature_blind_spot_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def _storage(*, missing_device: str | None, smart_device: str | None = None):
    devices = [
        {
            "pool": "HDDs",
            "vdev": "raidz1-0",
            "member_id": f"member-{bay}",
            "device": device,
            "physical_bay": bay,
            "present": True,
            "zfs_state": "ONLINE",
        }
        for bay, device in enumerate(("sda", "sdb", "sdc"), start=1)
    ]
    temperatures = [
        {"device": item["device"], "bay": item["physical_bay"], "temp": 35}
        for item in devices
        if item["device"] != missing_device
    ]
    smart = []
    if smart_device:
        item = next(record for record in devices if record["device"] == smart_device)
        smart.append(
            {
                **item,
                "drive": smart_device,
                "health": "PASSED",
                "pending": 2,
                "critical_warning": "0x00",
            }
        )
    return {"storage": {"devices": devices, "temperatures": temperatures, "smart": smart}}


def _cards(payload):
    cards = guidance_for_snapshot(payload) + temperature_guidance_for_snapshot(payload)
    for card in cards:
        card["recovery"] = recovery_contract(card)
    return cards


def test_known_present_member_without_temperature_is_not_silently_healthy():
    cards = _cards(_storage(missing_device="sdc"))

    assert [card["code"] for card in cards] == [
        "storage.temperature_telemetry_missing"
    ]
    evidence = cards[0]["runtime"]["evidence"]
    assert evidence["missing_member_count"] == 1
    assert evidence["missing_members"] == [
        {
            "pool": "HDDs",
            "vdev": "raidz1-0",
            "member_id": "member-3",
            "device": "sdc",
            "bay": 3,
            "zfs_state": "ONLINE",
        }
    ]
    assert evidence["temperature_state"] == "unknown"
    assert cards[0]["runtime"]["action_gate"]["destructive_actions_ready"] is False


def test_complete_or_non_authoritative_inventory_does_not_raise_blind_spot():
    assert _cards(_storage(missing_device=None)) == []
    assert temperature_guidance_for_snapshot({"storage": {"temperatures": []}}) == []
    assert guidance_for_snapshot(_storage(missing_device="sdc")) == []


def test_matching_smart_evidence_correlates_only_by_exact_member_identity():
    matched = correlate_incident(
        _cards(_storage(missing_device="sdc", smart_device="sdc")), {}
    )
    mismatch = correlate_incident(
        _cards(_storage(missing_device="sdc", smart_device="sda")), {}
    )

    assert matched is not None
    assert matched["incident_id"] == "aegis:drive-temperature-observability"
    assert matched["confidence"] == 0.84
    assert matched["confidence_basis"]["exact_member_identity"] == [
        "bay:3",
        "device:sdc",
    ]
    assert matched["confidence_basis"]["temperature_claim"] == "unknown"
    assert matched["consolidated_alert_count"] == 1
    assert matched["suppressed_duplicate_count"] == 1
    assert mismatch is not None
    assert mismatch["incident_id"] != "aegis:drive-temperature-observability"


def test_resolution_requires_three_complete_identity_stable_observations():
    base = {
        "code": "storage.temperature_telemetry_missing",
        "runtime": {
            "phase": "verify",
            "evidence": {
                "missing_member_count": 0,
                "identity_stable": True,
                "consecutive_complete_samples": 2,
            },
        },
    }
    assert verify_temperature_coverage(base)["status"] == "pending"
    base["runtime"]["evidence"]["consecutive_complete_samples"] = 3
    assert verify_temperature_coverage(base)["status"] == "passed"
    base["runtime"]["evidence"]["identity_stable"] = False
    assert verify_temperature_coverage(base)["status"] == "pending"


def test_coverage_candidate_has_nine_rehearsed_paths_without_installing_it():
    matrix = coverage_matrix(rehearse_recovery_paths())
    candidate = build_temperature_coverage_candidate(
        matrix,
        rehearse_temperature_coverage(),
    )
    entry = next(
        item
        for item in candidate["entries"]
        if item["code"] == "storage.temperature_telemetry_missing"
    )

    assert matrix["total"] == 8
    assert matrix["trusted"] == 8
    assert candidate["total"] == 9
    assert candidate["trusted"] == 9
    assert candidate["gaps"] == 0
    assert candidate["accepted"] is False
    assert candidate["installed"] is False
    assert candidate["automatic_acceptance"] is False
    assert candidate["status"] == "READY_FOR_OPERATOR_REVIEW"
    assert validate_temperature_coverage_candidate(candidate) == ()
    assert entry["coverage_state"] == "TRUSTED"
    assert entry["verification"]["strategy"] == "drive_temperature_inventory_recheck"
    assert entry["regression_scenarios"] == (
        "aegis-drive-temperature-blind-spot",
    )


def test_engine_preserves_accepted_matrix_and_exposes_unaccepted_candidate():
    result = AegisReliabilityEngine().observe({"operator_guidance": []})

    assert result["coverage_summary"] == {"total": 8, "trusted": 8, "gaps": 0}
    assert result["coverage_candidate"]["total"] == 9
    assert result["coverage_candidate"]["accepted"] is False
    assert result["coverage_candidate"]["installed"] is False


def test_holodeck_proof_avoids_the_isolated_threshold_false_negative():
    report = run_temperature_blind_spot_checkride()

    assert report["simulation"] is True
    assert report["hardware_isolated"] is True
    assert report["production_mutation"] is False
    assert report["measurements"] == {
        "scenario_count": 5,
        "aegis_detection_sample": 1,
        "isolated_temperature_threshold_sample": None,
        "isolated_temperature_alert_count": 0,
        "blind_spot_false_negatives_avoided": 1,
        "raw_actionable_alert_count": 2,
        "consolidated_incident_count": 1,
        "alert_reduction_percent": 50,
        "false_overheating_claims": 0,
        "cross_drive_false_correlations": 0,
        "runtime_writes": 0,
        "hardware_actions": 0,
    }
    assert report["black_box_evidence"]["frame_count"] == 2
    assert report["verification_rehearsal"]["status"] == "passed"


def test_preserved_blind_spot_evidence_replays_exactly():
    preserved = json.loads(
        (ROOT / "docs/evidence/aegis-temperature-blind-spot-v1.json").read_text()
    )
    assert preserved == run_temperature_blind_spot_checkride()


def test_mobile_reliability_view_names_unknown_temperature_boundary():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Temperature · UNKNOWN" in source
    assert "Missing is not cool" in source
    assert "Recovery Coverage Candidate" in source
    assert "UNACCEPTED · NOT INSTALLED" in source
    assert "@media(max-width:760px)" in source
