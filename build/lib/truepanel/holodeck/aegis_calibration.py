"""Deterministic calibration corpus for AEGIS incident correlation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from truepanel.aegis.correlation import correlate_incident
from truepanel.oracle import OracleEngine

from .oracle_lab import OracleLabScenario, OracleLabStep, fan_bearing_degradation


@dataclass(frozen=True)
class CalibrationCase:
    """One labeled scenario used to measure correlation behavior."""

    scenario: OracleLabScenario
    shared_cooling_expected: bool
    challenge: str


def _baseline() -> list[OracleLabStep]:
    return [
        OracleLabStep(
            {
                "fan.pwm": 180.0 + ((index % 3) - 1),
                "fan.rpm": 1500.0 + ((index % 5) - 2) * 4.0,
                "drive.temperature_c": 35.0,
                "cpu.temperature_c": 48.0,
            }
        )
        for index in range(12)
    ]


def ambient_temperature_rise() -> OracleLabScenario:
    """Temperatures drift together while fan delivery remains healthy."""

    steps = _baseline()
    for index in range(1, 25):
        steps.append(
            OracleLabStep(
                {
                    "fan.pwm": 180.0,
                    "fan.rpm": 1500.0,
                    "drive.temperature_c": 35.0 + index * 0.25,
                    "cpu.temperature_c": 48.0 + index * 0.45,
                }
            )
        )
    return OracleLabScenario("ambient-temperature-rise", tuple(steps))


def transient_rpm_sensor_spike() -> OracleLabScenario:
    """One implausible RPM sample must not become a shared-cause incident."""

    steps = _baseline()
    steps.append(
        OracleLabStep(
            {
                "fan.pwm": 180.0,
                "fan.rpm": 250.0,
                "drive.temperature_c": 35.0,
                "cpu.temperature_c": 48.0,
            }
        )
    )
    steps.extend(_baseline()[:6])
    return OracleLabScenario("transient-rpm-sensor-spike", tuple(steps))


def workload_temperature_rise() -> OracleLabScenario:
    """Load raises effort and temperature while delivered RPM also rises."""

    steps = _baseline()
    for index in range(1, 21):
        steps.append(
            OracleLabStep(
                {
                    "fan.pwm": min(255.0, 180.0 + index * 3.0),
                    "fan.rpm": 1500.0 + index * 12.0,
                    "drive.temperature_c": 35.0 + index * 0.12,
                    "cpu.temperature_c": 48.0 + index * 0.65,
                }
            )
        )
    return OracleLabScenario("workload-temperature-rise", tuple(steps))


def calibration_cases() -> tuple[CalibrationCase, ...]:
    return (
        CalibrationCase(
            fan_bearing_degradation(),
            True,
            "fan delivery falls while effort and downstream heat rise",
        ),
        CalibrationCase(
            ambient_temperature_rise(),
            False,
            "two thermal signals alone are not proof of fan degradation",
        ),
        CalibrationCase(
            transient_rpm_sensor_spike(),
            False,
            "one sensor excursion lacks corroborating effort or thermal evidence",
        ),
        CalibrationCase(
            workload_temperature_rise(),
            False,
            "healthy rising fan delivery distinguishes load from cooling loss",
        ),
    )


def _legacy_signal_count_match(outlook: dict) -> bool:
    """Model the pre-policy `two unusual cooling facts` heuristic."""

    signals = set(outlook.get("active_signals", ())) & {
        "fan.pwm",
        "fan.rpm",
        "drive.temperature_c",
        "cpu.temperature_c",
    }
    correlations = {
        item.get("key")
        for item in outlook.get("correlations", ())
        if isinstance(item, dict)
    } & {"cooling.efficiency", "chassis.airflow"}
    return len(signals) + len(correlations) >= 2


def run_correlation_calibration() -> dict:
    """Measure the policy against labeled positive and adversarial scenarios."""

    results = []
    true_positive = false_positive = true_negative = false_negative = 0
    legacy_false_positive = 0

    for case in calibration_cases():
        oracle = OracleEngine()
        first_policy_match = None
        first_legacy_match = None
        first_isolated_threshold = None
        for index, step in enumerate(case.scenario.steps):
            outlook = oracle.observe(
                timestamp=float(index),
                metrics=step.metrics,
                hard_faults=step.hard_faults,
            )
            if correlate_incident([], outlook) and first_policy_match is None:
                first_policy_match = index
            if _legacy_signal_count_match(outlook) and first_legacy_match is None:
                first_legacy_match = index
            isolated = (
                step.metrics.get("fan.rpm", 9999) <= 300
                or step.metrics.get("drive.temperature_c", 0) >= 42
                or step.metrics.get("cpu.temperature_c", 0) >= 70
            )
            if isolated and first_isolated_threshold is None:
                first_isolated_threshold = index

        predicted = first_policy_match is not None
        if case.shared_cooling_expected and predicted:
            true_positive += 1
        elif case.shared_cooling_expected:
            false_negative += 1
        elif predicted:
            false_positive += 1
        else:
            true_negative += 1
        if not case.shared_cooling_expected and first_legacy_match is not None:
            legacy_false_positive += 1
        results.append(
            {
                "scenario": case.scenario.name,
                "expected_shared_cooling": case.shared_cooling_expected,
                "first_policy_match_index": first_policy_match,
                "first_legacy_match_index": first_legacy_match,
                "first_isolated_threshold_index": first_isolated_threshold,
                "lead_samples": (
                    first_isolated_threshold - first_policy_match
                    if first_policy_match is not None
                    and first_isolated_threshold is not None
                    else None
                ),
                "challenge": case.challenge,
                "passed": predicted is case.shared_cooling_expected,
            }
        )

    precision = true_positive / (true_positive + false_positive) if true_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive else 0.0
    specificity = true_negative / (true_negative + false_positive) if true_negative else 0.0
    report = {
        "schema_version": 1,
        "scenario": "aegis-correlation-calibration-v1",
        "simulation": True,
        "hardware_isolated": True,
        "production_mutation": False,
        "corpus_size": len(results),
        "confusion_matrix": {
            "true_positive": true_positive,
            "false_positive": false_positive,
            "true_negative": true_negative,
            "false_negative": false_negative,
        },
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "specificity": round(specificity, 3),
        "legacy_false_positive_scenarios": legacy_false_positive,
        "results": results,
        "limitations": [
            "small deterministic corpus, not a production false-positive estimate",
            "aggregate chassis signals, not yet localized by fan zone or drive bay",
        ],
    }
    report["evidence_sha256"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return report


__all__ = [
    "ambient_temperature_rise",
    "calibration_cases",
    "run_correlation_calibration",
    "transient_rpm_sensor_spike",
    "workload_temperature_rise",
]
