#!/usr/bin/env python3
"""Regenerate the deterministic AEGIS Black Box fixture corpus."""

from __future__ import annotations

import hashlib
import json

from truepanel.history.black_box import BlackBoxFrame
from truepanel.holodeck.aegis_calibration import (
    ambient_temperature_rise,
    transient_rpm_sensor_spike,
    workload_temperature_rise,
)
from truepanel.holodeck.aegis_corpus import CORPUS_ID, builtin_corpus_path
from truepanel.holodeck.oracle_lab import (
    OracleLabScenario,
    OracleLabStep,
    fan_bearing_degradation,
)


def _baseline(count: int = 12) -> list[OracleLabStep]:
    return [
        OracleLabStep(
            {
                "fan.pwm": 180.0 + ((index % 3) - 1),
                "fan.rpm": 1500.0 + ((index % 5) - 2) * 4.0,
                "drive.temperature_c": 35.0,
                "cpu.temperature_c": 48.0,
            }
        )
        for index in range(count)
    ]


def telemetry_dropout() -> OracleLabScenario:
    steps = _baseline()
    steps.extend(
        OracleLabStep(
            {
                "fan.pwm": 180.0,
                "drive.temperature_c": 35.0 + index * 0.08,
                "cpu.temperature_c": 48.0 + index * 0.12,
            }
        )
        for index in range(12)
    )
    return OracleLabScenario("telemetry-dropout", tuple(steps))


def sensor_noise() -> OracleLabScenario:
    steps = _baseline()
    steps.extend(
        OracleLabStep(
            {
                "fan.pwm": 180.0,
                "fan.rpm": 1500.0 + (-1 if index % 2 else 1) * (60 + index * 3),
                "drive.temperature_c": 35.0 + (index % 3) * 0.1,
                "cpu.temperature_c": 48.0,
            }
        )
        for index in range(18)
    )
    return OracleLabScenario("fan-sensor-noise", tuple(steps))


CASES = (
    (fan_bearing_degradation(), True, "shared-cause-positive", 46),
    (ambient_temperature_rise(), False, "ambient-shift", None),
    (workload_temperature_rise(), False, "workload-shift", None),
    (transient_rpm_sensor_spike(), False, "transient-sensor-error", 12),
    (telemetry_dropout(), False, "telemetry-dropout", None),
    (sensor_noise(), False, "sensor-noise", None),
)


def _canonical(value) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def main() -> None:
    root = builtin_corpus_path()
    root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "corpus_id": CORPUS_ID,
        "source": "deterministic-synthetic",
        "privacy": "sanitized",
        "license": "MIT (TruePanel fixture data)",
        "generated_by": "development/tools/generate_aegis_corpus.py",
        "cases": [],
        "limitations": [
            "synthetic fixture recordings are not a production false-positive estimate",
            "aggregate chassis signals are not localized by fan zone or drive bay",
            "confidence weights require calibration against opt-in real incident recordings",
        ],
    }
    for scenario, expected, challenge, threshold in CASES:
        records = []
        for index, step in enumerate(scenario.steps):
            frame = BlackBoxFrame.capture(
                captured_at=float(index),
                sequence=index,
                telemetry={
                    "metrics": dict(step.metrics),
                    "hard_faults": list(step.hard_faults),
                },
                mission_control={"fixture": True, "case_id": scenario.name},
            )
            records.append(_canonical(frame.as_dict()))
        raw = b"\n".join(records) + b"\n"
        filename = f"{scenario.name}.jsonl"
        (root / filename).write_bytes(raw)
        manifest["cases"].append(
            {
                "case_id": scenario.name,
                "recording": filename,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "frame_count": len(records),
                "expected_shared_cooling": expected,
                "first_isolated_threshold_index": threshold,
                "challenge": challenge,
            }
        )
    manifest["corpus_sha256"] = hashlib.sha256(_canonical(manifest)).hexdigest()
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
