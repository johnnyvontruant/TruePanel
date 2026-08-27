"""Deterministic HoloDeck proof for AEGIS shared-cause correlation."""

from __future__ import annotations

import hashlib
import json

from truepanel.aegis.correlation import correlate_incident
from truepanel.aegis.rehearsal import rehearse_recovery_paths
from truepanel.history.black_box import BlackBoxFrame
from truepanel.oracle import OracleEngine

from .oracle_lab import fan_bearing_degradation


def run_shared_cooling_experiment() -> dict:
    """Compare AEGIS correlation with lab-only isolated thresholds."""

    scenario = fan_bearing_degradation()
    oracle = OracleEngine()
    first_aegis = None
    first_isolated = None
    terminal_independent_alerts: list[str] = []
    key_evidence = []
    black_box_frames = []

    for index, step in enumerate(scenario.steps):
        outlook = oracle.observe(
            timestamp=float(index),
            metrics=step.metrics,
            hard_faults=step.hard_faults,
        )
        incident = correlate_incident([], outlook)
        isolated = []
        if step.metrics.get("fan.rpm", 9999) <= 300:
            isolated.append("cooling.fan_stall")
        if step.metrics.get("drive.temperature_c", 0) >= 42:
            isolated.append("thermal.drive_temperature_high")
        if step.metrics.get("cpu.temperature_c", 0) >= 70:
            isolated.append("thermal.cpu_temperature_high")

        if incident and first_aegis is None:
            first_aegis = index
            key_evidence.append(
                {
                    "event": "aegis_shared_cause_identified",
                    "sample": index,
                    "likely_cause": incident["likely_cause"],
                    "confidence": incident["confidence"],
                    "signals": [item["signal"] for item in incident["supporting_signals"]],
                }
            )
            black_box_frames.append(
                BlackBoxFrame.capture(
                    captured_at=float(index),
                    sequence=len(black_box_frames),
                    telemetry=step.metrics,
                    mission_control={"reliability": {"active_incident": incident}},
                ).as_dict()
            )
        if isolated and first_isolated is None:
            first_isolated = index
            key_evidence.append(
                {
                    "event": "first_isolated_threshold",
                    "sample": index,
                    "alerts": isolated,
                }
            )
            black_box_frames.append(
                BlackBoxFrame.capture(
                    captured_at=float(index),
                    sequence=len(black_box_frames),
                    telemetry=step.metrics,
                    alerts=[{"code": code, "severity": "warning"} for code in isolated],
                    mission_control={"reliability": {"active_incident": incident}},
                ).as_dict()
            )
        terminal_independent_alerts = isolated

    lead_samples = (
        first_isolated - first_aegis
        if first_aegis is not None and first_isolated is not None
        else None
    )
    rehearsal = rehearse_recovery_paths()["cooling.fan_stall"]
    report = {
        "schema_version": 1,
        "scenario": "aegis-shared-cooling-degradation",
        "simulation": True,
        "hardware_isolated": True,
        "production_mutation": False,
        "samples": len(scenario.steps),
        "first_aegis_shared_cause_index": first_aegis,
        "first_isolated_threshold_index": first_isolated,
        "lead_samples": lead_samples,
        "identified_earlier": lead_samples is not None and lead_samples > 0,
        "terminal_independent_alert_count": len(terminal_independent_alerts),
        "aegis_incident_count": 1 if first_aegis is not None else 0,
        "alert_reduction_percent": (
            round((len(terminal_independent_alerts) - 1) / len(terminal_independent_alerts) * 100)
            if terminal_independent_alerts
            else 0
        ),
        "likely_cause": "Shared chassis cooling degradation",
        "verification_rehearsal": rehearsal,
        "evidence": key_evidence,
        "black_box_evidence": {
            "privacy": "sanitized",
            "frame_count": len(black_box_frames),
            "frames": black_box_frames,
        },
        "lab_only_thresholds": {
            "fan_rpm_at_or_below": 300,
            "drive_temperature_c_at_or_above": 42,
            "cpu_temperature_c_at_or_above": 70,
        },
    }
    digest_source = dict(report)
    report["evidence_sha256"] = hashlib.sha256(
        json.dumps(digest_source, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return report


__all__ = ["run_shared_cooling_experiment"]
