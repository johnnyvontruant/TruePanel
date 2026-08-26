"""Deterministic slow-degradation laboratory for Project ORACLE."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from truepanel.oracle.engine import OracleEngine, OracleState


@dataclass(frozen=True)
class OracleLabStep:
    """One deterministic telemetry observation in an ORACLE experiment."""

    metrics: Mapping[str, float]
    hard_faults: tuple[str, ...] = ()


@dataclass(frozen=True)
class OracleLabScenario:
    """A bounded what-happens-before-the-watcher-fires experiment."""

    name: str
    steps: tuple[OracleLabStep, ...]


def fan_bearing_degradation() -> OracleLabScenario:
    """Model a fan that slowly loses delivered RPM as effort increases."""

    steps = []
    for index in range(12):
        steps.append(
            OracleLabStep(
                {
                    "fan.pwm": 180.0 + ((index % 3) - 1),
                    "fan.rpm": 1500.0 + ((index % 5) - 2) * 4.0,
                    "drive.temperature_c": 35.0,
                    "cpu.temperature_c": 48.0,
                }
            )
        )

    for index in range(1, 41):
        rpm = max(250.0, 1500.0 - index * 32.0)
        hard = ("fan.rpm",) if rpm <= 300.0 else ()
        steps.append(
            OracleLabStep(
                {
                    "fan.pwm": 180.0 + index * 2.5,
                    "fan.rpm": rpm,
                    "drive.temperature_c": 35.0 + index * 0.20,
                    "cpu.temperature_c": 48.0,
                },
                hard_faults=hard,
            )
        )

    return OracleLabScenario("fan-bearing-degradation", tuple(steps))


def drive_degradation() -> OracleLabScenario:
    """Model latency/temperature drift before a conventional media fault."""

    steps = []
    for index in range(12):
        steps.append(
            OracleLabStep(
                {
                    "drive.latency_ms": 8.0 + ((index % 3) - 1) * 0.05,
                    "drive.temperature_c": 35.0,
                    "drive.smart_reallocated": 0.0,
                }
            )
        )

    for index in range(1, 25):
        # The final observation represents a separate conventional SMART/media
        # threshold becoming actionable.  ORACLE should already have raised a
        # WATCH/DEVELOPING signal from the preceding drift.
        hard = ("drive.latency_ms",) if index == 24 else ()
        steps.append(
            OracleLabStep(
                {
                    "drive.latency_ms": 8.0 + index * 0.40,
                    "drive.temperature_c": 35.0 + index * 0.25,
                    "drive.smart_reallocated": float(max(0, index - 8)),
                },
                hard_faults=hard,
            )
        )

    return OracleLabScenario("drive-slow-degradation", tuple(steps))


def network_path_degradation() -> OracleLabScenario:
    """Model growing link errors followed by a negotiated-speed collapse."""

    steps = []
    for _ in range(12):
        steps.append(
            OracleLabStep(
                {
                    "network.link_mbps": 1000.0,
                    "network.errors": 0.0,
                }
            )
        )

    for index in range(1, 21):
        link = 1000.0 if index < 10 else 100.0
        hard = ("network.link_mbps",) if index == 20 else ()
        steps.append(
            OracleLabStep(
                {
                    "network.link_mbps": link,
                    "network.errors": float(index * 2),
                },
                hard_faults=hard,
            )
        )

    return OracleLabScenario("network-path-degradation", tuple(steps))


def run_oracle_scenario(scenario: OracleLabScenario) -> dict:
    """Run one slow-degradation experiment through the real ORACLE engine."""

    engine = OracleEngine()
    first_signal = None
    hard_fault = None
    peak_state = OracleState.NORMAL
    correlations = set()

    for index, step in enumerate(scenario.steps):
        outlook = engine.observe(
            timestamp=float(index),
            metrics=step.metrics,
            hard_faults=step.hard_faults,
        )
        state = OracleState(outlook["state"])
        if state.value != OracleState.NORMAL.value and first_signal is None:
            first_signal = index
        if step.hard_faults and hard_fault is None:
            hard_fault = index
        if state_order(state) > state_order(peak_state):
            peak_state = state
        correlations.update(
            item["key"]
            for item in outlook.get("correlations", [])
            if isinstance(item, dict) and item.get("key")
        )

    lead_samples = None
    if first_signal is not None and hard_fault is not None:
        lead_samples = hard_fault - first_signal

    return {
        "scenario": scenario.name,
        "simulation": True,
        "production_mutation": False,
        "first_oracle_signal_index": first_signal,
        "hard_fault_index": hard_fault,
        "lead_samples": lead_samples,
        "early_warning": (
            first_signal is not None
            and hard_fault is not None
            and first_signal < hard_fault
        ),
        "peak_state": peak_state.value,
        "correlations": sorted(correlations),
    }


def state_order(state: OracleState) -> int:
    return {
        OracleState.NORMAL: 0,
        OracleState.WATCH: 1,
        OracleState.DEVELOPING: 2,
        OracleState.FAULT: 3,
    }[state]


def run_oracle_lab() -> list[dict]:
    """Run the bounded first ORACLE HoloDeck experiment set."""

    return [
        run_oracle_scenario(fan_bearing_degradation()),
        run_oracle_scenario(drive_degradation()),
        run_oracle_scenario(network_path_degradation()),
    ]
