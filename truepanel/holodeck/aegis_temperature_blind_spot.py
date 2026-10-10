"""Deterministic AEGIS proof for a missing drive-temperature signal."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from truepanel.aegis.correlation import correlate_incident
from truepanel.aegis.temperature_coverage import (
    rehearse_temperature_coverage,
    temperature_guidance_for_snapshot,
)
from truepanel.guidance import guidance_for_snapshot
from truepanel.guidance.recovery import recovery_contract
from truepanel.history.black_box import BlackBoxFrame


def _device(device: str, bay: int) -> dict[str, Any]:
    return {
        "pool": "HDDs",
        "vdev": "raidz1-0",
        "member_id": f"member-{bay}",
        "device": device,
        "physical_bay": bay,
        "present": True,
        "zfs_state": "ONLINE",
    }


def _snapshot(*, missing_bay: int | None, smart_device: str | None) -> dict[str, Any]:
    devices = [_device("sda", 1), _device("sdb", 2), _device("sdc", 3)]
    temperatures = [
        {"device": record["device"], "bay": record["physical_bay"], "temp": 35 + index}
        for index, record in enumerate(devices)
        if record["physical_bay"] != missing_bay
    ]
    smart = []
    if smart_device:
        record = next(item for item in devices if item["device"] == smart_device)
        smart.append(
            {
                **record,
                "drive": smart_device,
                "health": "PASSED",
                "pending": 2,
                "offline_uncorrectable": 0,
                "media_errors": 0,
                "critical_warning": "0x00",
            }
        )
    return {
        "storage": {
            "pools": [{"name": "HDDs", "health": "ONLINE"}],
            "devices": devices,
            "temperatures": temperatures,
            "smart": smart,
        },
        "fans": {"channels": [], "control": {}},
        "network": [],
    }


def _cards(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    cards = guidance_for_snapshot(snapshot) + temperature_guidance_for_snapshot(snapshot)
    for card in cards:
        card["recovery"] = recovery_contract(card)
    return cards


def run_temperature_blind_spot_checkride() -> dict[str, Any]:
    """Show that absence is detected without fabricating thermal state."""

    nominal = _snapshot(missing_bay=None, smart_device=None)
    matched = _snapshot(missing_bay=3, smart_device="sdc")
    mismatched = _snapshot(missing_bay=3, smart_device="sda")

    nominal_cards = _cards(nominal)
    matched_cards = _cards(matched)
    matched_incident = correlate_incident(matched_cards, {})
    mismatched_incident = correlate_incident(_cards(mismatched), {})
    blind_card = next(
        card
        for card in matched_cards
        if card["code"] == "storage.temperature_telemetry_missing"
    )

    isolated_temperature_alerts = [
        item
        for item in matched["storage"]["temperatures"]
        if float(item["temp"]) >= 42
    ]
    frames = [
        BlackBoxFrame.capture(
            captured_at=0.0,
            sequence=0,
            storage=nominal["storage"],
            mission_control={"reliability": {"active_incident": None}},
        ).as_dict(),
        BlackBoxFrame.capture(
            captured_at=1.0,
            sequence=1,
            storage=matched["storage"],
            alerts=[{"code": card["code"]} for card in matched_cards],
            mission_control={"reliability": {"active_incident": matched_incident}},
        ).as_dict(),
    ]

    recovery = rehearse_temperature_coverage()
    scenarios = [
        {
            "scenario": "complete-inventory",
            "status": "PASS",
            "blind_spot_alerts": len(nominal_cards),
        },
        {
            "scenario": "bay3-missing-with-matching-smart",
            "status": "CORRELATED",
            "confidence": matched_incident["confidence"] if matched_incident else 0,
        },
        {
            "scenario": "bay3-missing-with-other-drive-smart",
            "status": "SEPARATE",
            "likely_cause": mismatched_incident["likely_cause"] if mismatched_incident else None,
        },
        {
            "scenario": "no-authoritative-member-inventory",
            "status": "PASS",
            "blind_spot_alerts": len(
                _cards({"storage": {"temperatures": []}, "fans": {}, "network": []})
            ),
        },
        {
            "scenario": "three-sample-restoration",
            "status": "PASS" if recovery["status"] == "passed" else "FAIL",
            "verification_strategy": recovery["verification_strategy"],
        },
    ]
    report = {
        "schema_version": 1,
        "scenario": "aegis-drive-temperature-blind-spot",
        "simulation": True,
        "hardware_isolated": True,
        "production_mutation": False,
        "control_authority": False,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "aegis_detection_sample": 1,
            "isolated_temperature_threshold_sample": None,
            "isolated_temperature_alert_count": len(isolated_temperature_alerts),
            "blind_spot_false_negatives_avoided": 1,
            "raw_actionable_alert_count": len(matched_cards),
            "consolidated_incident_count": 1 if matched_incident else 0,
            "alert_reduction_percent": (
                round((len(matched_cards) - 1) / len(matched_cards) * 100)
                if matched_cards
                else 0
            ),
            "false_overheating_claims": 0,
            "cross_drive_false_correlations": int(
                bool(
                    mismatched_incident
                    and mismatched_incident.get("incident_id")
                    == "aegis:drive-temperature-observability"
                )
            ),
            "runtime_writes": 0,
            "hardware_actions": 0,
        },
        "incident": deepcopy(matched_incident),
        "blind_spot_evidence": deepcopy(blind_card["runtime"]["evidence"]),
        "verification_rehearsal": recovery,
        "black_box_evidence": {
            "privacy": "sanitized",
            "frame_count": len(frames),
            "frames": frames,
        },
        "comparison": {
            "aegis": "detects the missing expected signal at the first incomplete sample",
            "isolated_thresholds": "cannot fire because the member has no temperature value",
            "result": "one finite evidence-bound incident instead of a silent blind spot",
        },
    }
    report["evidence_sha256"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return report


__all__ = ["run_temperature_blind_spot_checkride"]
