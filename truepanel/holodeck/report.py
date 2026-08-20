"""Deterministic mission execution and compact HoloDeck flight reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .catalog import host_fixture
from .invariants import evaluate_timeline
from .missions import mission_scenario
from .provider import HoloDeckHostProvider
from .runner import HoloDeckScenarioRunner


def run_mission_report(
    name: str,
    *,
    runtime_dir: str | Path,
) -> dict[str, Any]:
    """Run every transition in a built-in mission and return a safe summary.

    The report intentionally excludes raw host snapshots.  It records only
    deterministic mission metadata, invariant outcomes, event counts, and
    high-level terminal state useful to CI and operator review.
    """

    scenario = mission_scenario(name)
    provider = HoloDeckHostProvider(
        host_fixture(scenario.host),
        scenario=scenario,
    )
    runner = HoloDeckScenarioRunner(
        provider,
        runtime_dir=runtime_dir,
    )

    observations = [runner.step()]
    previous_time = 0.0
    for event_time in sorted({event.at for event in scenario.events}):
        observations.append(runner.step(event_time - previous_time))
        previous_time = event_time

    invariant_result = evaluate_timeline(observations)
    final = observations[-1]
    pools = {
        str(pool.get("name")): str(pool.get("health", "UNKNOWN"))
        for pool in final.state.get("pools", [])
        if isinstance(pool, dict)
    }
    fan_events = sum(
        1
        for observation in observations
        for event in observation.events
        if "fan" in str(getattr(event, "source", "")).lower()
        or "fan" in str(getattr(event, "kind", "")).lower()
    )
    storage_events = sum(
        1
        for observation in observations
        for event in observation.events
        if "storage" in str(getattr(event, "source", "")).lower()
        or "storage" in str(getattr(event, "kind", "")).lower()
    )

    return {
        "mission": scenario.name,
        "host": scenario.host,
        "simulated_seconds": previous_time,
        "scenario_event_count": len(scenario.events),
        "observation_count": len(observations),
        "mission_event_count": sum(len(item.events) for item in observations),
        "fan_event_count": fan_events,
        "storage_event_count": storage_events,
        "invariants": {
            "passed": invariant_result.passed,
            "rule_count": invariant_result.rule_count,
            "violation_count": len(invariant_result.violations),
            "violations": [
                {
                    "rule_id": item.rule_id,
                    "observation_index": item.observation_index,
                }
                for item in invariant_result.violations
            ],
        },
        "final": {
            "cpu_temperature_c": final.state.get("cpu_temperature_c"),
            "telemetry_fresh": bool(final.state.get("telemetry_fresh", False)),
            "lcd_connected": bool(final.state.get("lcd", {}).get("connected", False)),
            "primary_network_up": bool(
                final.state.get("network", {}).get("enp116s0", {}).get("link_up", False)
            ),
            "pool_health": pools,
        },
    }


__all__ = ["run_mission_report"]
