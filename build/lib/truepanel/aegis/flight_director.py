"""Hardware-isolated Flight Director proof for the shared-cooling incident."""

from __future__ import annotations

import hashlib
import json
import math
from statistics import fmean
from typing import Any

from truepanel.guidance.recovery import verification_for_card
from truepanel.holodeck.oracle_lab import fan_bearing_degradation
from truepanel.oracle import OracleEngine

from .correlation import correlate_incident

DRIVE_WARNING_C = 42.0


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _linear_forecast(samples: list[dict[str, float]], threshold: float) -> dict[str, Any]:
    xs = [item["sample"] for item in samples]
    ys = [item["value"] for item in samples]
    x_mean, y_mean = fmean(xs), fmean(ys)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys, strict=True)) / denominator
    intercept = y_mean - slope * x_mean
    residuals = [y - (intercept + slope * x) for x, y in zip(xs, ys, strict=True)]
    rmse = math.sqrt(fmean(value * value for value in residuals))
    crossing = None
    if slope > 0:
        crossing = int(math.ceil(((threshold - intercept) / slope) - 1e-9))
    return {
        "metric": "drive.temperature_c",
        "trajectory_c_per_sample": round(slope, 3),
        "threshold_c": threshold,
        "estimated_crossing_sample": crossing,
        "uncertainty_samples": 2,
        "fixture_fit_rmse_c": round(rmse, 3),
        "calibration_maturity": "deterministic_lab_only",
        "precision_disclosure": "The point estimate fits a linear fixture; ±2 samples is a policy floor, not a field confidence interval.",
    }


def _topology() -> dict[str, Any]:
    nodes = [
        ("cause:shared-cooling", "probable_cause", "Shared cooling degradation", "probable"),
        ("fan:unknown", "fan_channel", "Affected fan channel unknown", "unknown"),
        ("zone:chassis", "cooling_zone", "Aggregate chassis zone", "observed"),
        ("sensor:fan-rpm", "sensor", "Aggregate fan RPM", "observed"),
        ("sensor:drive-temp", "sensor", "Hottest drive temperature", "observed"),
        ("bay:unknown", "drive_bay", "Affected bay not present in fixture", "unknown"),
        ("drive:unknown", "drive", "Drive identity not present in fixture", "unknown"),
        ("vdev:unknown", "vdev", "VDEV membership not present in fixture", "unknown"),
        ("pool:unknown", "pool", "Pool membership not present in fixture", "unknown"),
        ("workload:unknown", "workload", "Workload class not recorded", "unknown"),
        ("service:truepanel", "service", "TruePanel passive observer", "known"),
        ("alert:fan", "alert", "cooling.fan_stall", "known"),
        ("alert:thermal", "alert", "thermal.high_temperature", "known"),
    ]
    edges = [
        ("fan:unknown", "sensor:fan-rpm", "measured_by"),
        ("fan:unknown", "zone:chassis", "cools"),
        ("zone:chassis", "sensor:drive-temp", "influences"),
        ("sensor:drive-temp", "bay:unknown", "location_unresolved"),
        ("bay:unknown", "drive:unknown", "contains_unresolved"),
        ("drive:unknown", "vdev:unknown", "membership_unresolved"),
        ("vdev:unknown", "pool:unknown", "membership_unresolved"),
        ("workload:unknown", "zone:chassis", "heat_load_unresolved"),
        ("service:truepanel", "alert:fan", "reports"),
        ("service:truepanel", "alert:thermal", "reports"),
        ("cause:shared-cooling", "fan:unknown", "hypothesizes"),
        ("cause:shared-cooling", "alert:fan", "explains"),
        ("cause:shared-cooling", "alert:thermal", "explains"),
    ]
    return {
        "nodes": [
            {"id": node_id, "kind": kind, "label": label, "certainty": certainty}
            for node_id, kind, label, certainty in nodes
        ],
        "edges": [
            {"source": source, "target": target, "relation": relation}
            for source, target, relation in edges
        ],
        "unknowns_are_explicit": True,
    }


def _what_if_rehearsals(detection_sample: int) -> list[dict[str, Any]]:
    rehearsals = [
        {
            "choice": "workload_returns_to_idle",
            "result": "thermal margin improves but fan-delivery evidence remains; keep incident open",
            "projected_threshold_crossing_sample": detection_sample + 41,
            "verification": "temperature slope falls below 0.10 C/sample while RPM does not worsen",
        },
        {
            "choice": "fan_degrades_further",
            "result": "unsafe envelope closes sooner; abort nonessential workload before threshold",
            "projected_threshold_crossing_sample": detection_sample + 18,
            "verification": "RPM slope remains negative and drive-temperature slope exceeds 0.25 C/sample",
        },
        {
            "choice": "airflow_restored",
            "result": "RPM recovers and both thermal trajectories reverse",
            "projected_threshold_crossing_sample": None,
            "verification": "five samples of positive RPM with declining drive temperature",
        },
    ]
    for item in rehearsals:
        item.update(
            {
                "simulation": True,
                "hardware_isolated": True,
                "control_authority": False,
            }
        )
        item["evidence_sha256"] = _digest(item)
    return rehearsals


def _recovery_plan() -> dict[str, Any]:
    return {
        "owners": ["AEGIS", "ORACLE", "Pathfinder", "Lifeline"],
        "affected_component": "fan channel unresolved from aggregate fixture",
        "affected_bay": None,
        "identity_verification": [
            "Map the monitored fan tachometer label to a physical channel before service.",
            "If a drive is implicated, match bay, serial fingerprint, pool, and VDEV through Lifeline before touching it.",
        ],
        "redundancy_and_backup_context": "Unknown in this fixture; do not infer pool redundancy or backup currency.",
        "safest_action": "Reduce avoidable thermal load, inspect external airflow, and verify fan identity; do not actuate or replace hardware from this lab result.",
        "expected_recovery_observations": [
            "fan RPM becomes stable and non-zero",
            "drive-temperature slope becomes negative",
            "shared-cooling hypothesis confidence decays",
            "thermal and fan alerts clear independently",
        ],
        "abort_conditions": [
            "temperature crosses the configured hard limit",
            "fan identity cannot be proven",
            "storage redundancy or backup state is unknown before disk service",
            "telemetry becomes stale or contradictory",
        ],
        "completion_criteria": [
            "five consecutive recovered-airflow samples",
            "drive temperature declines across the verification window",
            "fan verifier passes and no hard thermal fault remains",
        ],
        "advisory_only": True,
        "control_authority": False,
    }


def run_flight_director_proof() -> dict[str, Any]:
    """Replay, forecast, rehearse, and verify one complete lab-only incident."""

    scenario = fan_bearing_degradation()
    oracle = OracleEngine()
    first_incident: int | None = None
    first_threshold: int | None = None
    incident: dict[str, Any] | None = None
    replay = []
    incident_confidences = []
    terminal_alerts: list[str] = []
    for index, step in enumerate(scenario.steps):
        outlook = oracle.observe(
            timestamp=float(index), metrics=step.metrics, hard_faults=step.hard_faults
        )
        current = correlate_incident([], outlook)
        alerts = []
        if step.metrics["fan.rpm"] <= 300:
            alerts.append("cooling.fan_stall")
        if step.metrics["drive.temperature_c"] >= DRIVE_WARNING_C:
            alerts.append("thermal.high_temperature")
        if current and first_incident is None:
            first_incident, incident = index, current
        if current:
            incident_confidences.append(float(current["confidence"]))
        if alerts and first_threshold is None:
            first_threshold = index
        terminal_alerts = alerts
        replay.append(
            {
                "sample": index,
                "fan_rpm": step.metrics["fan.rpm"],
                "fan_pwm": step.metrics["fan.pwm"],
                "drive_temperature_c": step.metrics["drive.temperature_c"],
                "incident_active": current is not None,
                "isolated_alerts": alerts,
            }
        )
    if first_incident is None or first_threshold is None or incident is None:
        raise RuntimeError("Flight Director fixture did not produce the expected incident")

    fit = [
        {"sample": float(item["sample"]), "value": float(item["drive_temperature_c"])}
        for item in replay[max(0, first_incident - 5) : first_incident + 1]
    ]
    forecast = _linear_forecast(fit, DRIVE_WARNING_C)
    forecast["observed_crossing_sample"] = first_threshold
    forecast["absolute_error_samples"] = abs(
        first_threshold - int(forecast["estimated_crossing_sample"])
    )
    forecast["supporting_samples"] = [int(item["sample"]) for item in fit]

    restored = [
        {"sample": len(replay) + offset, "fan_rpm": 700 + offset * 180, "drive_temperature_c": 42.8 - offset * 0.45}
        for offset in range(5)
    ]
    fan_verification = verification_for_card(
        {"code": "cooling.fan_stall", "runtime": {"evidence": {"current_rpm": restored[-1]["fan_rpm"]}}}
    )
    observed_signature = {
        "sample_count": len(restored),
        "fan_positive": all(item["fan_rpm"] > 0 for item in restored),
        "drive_temperature_declining": all(
            after["drive_temperature_c"] < before["drive_temperature_c"]
            for before, after in zip(restored, restored[1:], strict=False)
        ),
        "fan_verifier": fan_verification["status"],
    }
    verification = {
        "expected_signature": {
            "minimum_samples": 5,
            "fan_positive": True,
            "drive_temperature_declining": True,
            "fan_verifier": "passed",
        },
        "observed_signature": observed_signature,
        "outcome": "passed" if all(
            (
                observed_signature["sample_count"] >= 5,
                observed_signature["fan_positive"],
                observed_signature["drive_temperature_declining"],
                observed_signature["fan_verifier"] == "passed",
            )
        ) else "failed",
        "evidence_sha256": _digest(restored),
    }
    report = {
        "schema_version": 1,
        "project": "FLIGHT_DIRECTOR",
        "scenario": "fan-degradation-shared-cooling-v1",
        "simulation": True,
        "hardware_isolated": True,
        "field_validated": False,
        "production_validated": False,
        "control_authority": False,
        "incident_time_machine": {
            "source": "deterministic Black Box-compatible telemetry",
            "replay": replay,
            "landmarks": [
                {"sample": 0, "event": "baseline begins"},
                {"sample": first_incident, "event": "shared cooling cause identified"},
                {"sample": first_threshold, "event": "first isolated threshold fires"},
                {"sample": len(replay) - 1, "event": "fixture terminal observation"},
            ],
        },
        "active_incident": incident,
        "causal_hardware_map": _topology(),
        "safe_operating_envelope": forecast,
        "what_if_rehearsals": _what_if_rehearsals(first_incident),
        "recovery_flight_plan": _recovery_plan(),
        "repair_verification_signature": verification,
        "measurements": {
            "shared_cause_detection_sample": first_incident,
            "first_isolated_threshold_sample": first_threshold,
            "detection_lead_samples": first_threshold - first_incident,
            "forecast_absolute_error_samples": forecast["absolute_error_samples"],
            "root_cause_stability": round(
                len(incident_confidences) / (len(replay) - first_incident), 3
            ),
            "terminal_isolated_alert_count": len(terminal_alerts),
            "correlated_incident_count": 1,
            "alert_reduction_percent": round(
                (len(terminal_alerts) - 1) / len(terminal_alerts) * 100
            ) if terminal_alerts else 0,
            "repair_verification_outcome": verification["outcome"],
            "timeline_clarity": "one cause, four landmarks, raw thresholds retained",
            "topology_clarity": "13 nodes; 6 unresolved identities are labeled unknown rather than guessed",
        },
        "hangar_update": {
            "experiment_id": "TP-EXP-0013",
            "successful_paths": ["correlation", "bounded forecast", "restored-airflow signature"],
            "failed_paths": ["exact fan channel inference", "bay/drive/pool inference", "field confidence claim"],
        },
    }
    report["evidence_sha256"] = _digest(report)
    return report


__all__ = ["run_flight_director_proof"]
