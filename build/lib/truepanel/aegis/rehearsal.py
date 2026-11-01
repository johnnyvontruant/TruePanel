"""Deterministic, hardware-isolated recovery verification rehearsals."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from truepanel.guidance.catalog import guidance_codes
from truepanel.guidance.recovery import verification_for_card

_REHEARSAL_EVIDENCE: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {
    "cooling.fan_stall": (
        {"current_rpm": 0},
        {"current_rpm": 1490},
    ),
    "thermal.high_temperature": (
        {"current_temperature_c": 76.0, "recovery_threshold_c": 70.0},
        {"current_temperature_c": 66.0, "recovery_threshold_c": 70.0},
    ),
    "storage.smart_warning": (
        {
            "smart_health": "FAILED",
            "pending": 2,
            "offline_uncorrectable": 1,
            "media_errors": 0,
            "critical_warning": "0x00",
            "zfs_state": "ONLINE",
        },
        {
            "smart_health": "PASSED",
            "pending": 0,
            "offline_uncorrectable": 0,
            "media_errors": 0,
            "critical_warning": "0x00",
            "zfs_state": "ONLINE",
        },
    ),
    "storage.disk_faulted": (
        {"pool_state": "DEGRADED", "resilver_state": {"resilver_running": True}},
        {"pool_state": "ONLINE", "resilver_state": {"resilver_running": False}},
    ),
    "storage.pool_degraded": (
        {"pool_state": "DEGRADED", "resilver_state": {"resilver_running": True}},
        {"pool_state": "ONLINE", "resilver_state": {"resilver_running": False}},
    ),
    "network.link_down": (
        {"link_up": False, "address": None},
        {"link_up": True, "address": "192.0.2.10"},
    ),
    "front_panel.lcd_unavailable": (
        {"reader_connected": False, "dispatcher_alive": False},
        {"reader_connected": True, "dispatcher_alive": True},
    ),
    "telemetry.stale": (
        {
            "telemetry_fresh": False,
            "missing_domains": ["hwmon"],
            "safety_hold": True,
        },
        {
            "telemetry_fresh": True,
            "missing_domains": [],
            "safety_hold": False,
        },
    ),
}


def _card(code: str, evidence: dict[str, Any]) -> dict[str, Any]:
    return {"code": code, "runtime": {"phase": "verify", "evidence": evidence}}


def rehearse_recovery_paths() -> dict[str, dict[str, Any]]:
    """Exercise every verifier from fault-present to recovered evidence."""

    report: dict[str, dict[str, Any]] = {}
    for code in guidance_codes():
        pair = _REHEARSAL_EVIDENCE.get(code)
        if pair is None:
            report[code] = {
                "status": "missing",
                "simulation": True,
                "production_mutation": False,
            }
            continue
        before_evidence, after_evidence = deepcopy(pair)
        before = verification_for_card(_card(code, before_evidence))
        after = verification_for_card(_card(code, after_evidence))
        passed = before.get("status") == "pending" and after.get("status") == "passed"
        evidence = {
            "code": code,
            "simulation": True,
            "production_mutation": False,
            "verification_strategy": after.get("strategy"),
            "fault_present_result": before.get("status"),
            "recovered_result": after.get("status"),
        }
        digest = hashlib.sha256(
            json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        report[code] = {
            **evidence,
            "status": "passed" if passed else "failed",
            "evidence_sha256": digest,
        }
    return report


__all__ = ["rehearse_recovery_paths"]
