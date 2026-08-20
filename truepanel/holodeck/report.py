"""Deterministic mission execution and compact HoloDeck flight reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .acceptance import acceptance_payload
from .catalog import host_fixture
from .invariants import evaluate_timeline
from .missions import mission_names, mission_scenario
from .provider import HoloDeckHostProvider
from .runner import HoloDeckScenarioRunner
from .temporal import temporal_payload


DEFAULT_OBSERVATION_INTERVAL_SECONDS = 10.0


def _observation_schedule(
    scenario,
    *,
    interval: float = DEFAULT_OBSERVATION_INTERVAL_SECONDS,
) -> list[float]:
    event_times = sorted({float(event.at) for event in scenario.events})
    if not event_times:
        return [0.0]
    end_time = event_times[-1]
    schedule = {0.0, *event_times}
    tick = float(interval)
    while tick < end_time:
        schedule.add(tick)
        tick += float(interval)
    return sorted(schedule)


def _terminal_contract(name: str, state: dict[str, Any], recommendations: list[str]) -> list[dict[str, Any]]:
    fans = state.get("fans", {}).get("fan_channels", [])
    fan_one = next((item for item in fans if int(item.get("number", -1)) == 1), {})
    bay_three = next((item for item in state.get("enclosure", {}).get("bays", []) if int(item.get("bay", -1)) == 3), {})
    pools = {str(pool.get("name")): str(pool.get("health", "UNKNOWN")) for pool in state.get("pools", []) if isinstance(pool, dict)}
    checks = {
        "thermal-ramp": [
            ("cpu_temperature_recovered", state.get("cpu_temperature_c"), 54.0),
            ("thermal_escalated_to_afterburners", "afterburners" in recommendations, True),
            ("thermal_downshifted_after_peak", recommendations[-1] if recommendations else None, "cooling_boost"),
        ],
        "fan-stall-recovery": [("fan_1_recovered", bool(fan_one.get("rpm", 0) > 0 and not fan_one.get("alarm", False)), True)],
        "drive-failure": [("drive_3_faulted_pool_degraded", (str(bay_three.get("health", "")).upper(), pools.get("HDDs")), ("FAULTED", "DEGRADED"))],
        "drive-failure-recovery": [("drive_3_recovered_pool_online", (str(bay_three.get("health", "")).upper(), bool(bay_three.get("present", False)), pools.get("HDDs")), ("ONLINE", True, "ONLINE"))],
        "drive-removal": [("drive_3_removed_pool_degraded", (bool(bay_three.get("present", True)), pools.get("HDDs")), (False, "DEGRADED"))],
        "drive-removal-reinsert": [("drive_3_reinserted_pool_online", (bool(bay_three.get("present", False)), bool(bay_three.get("device")), str(bay_three.get("health", "")).upper(), pools.get("HDDs")), (True, True, "ONLINE", "ONLINE"))],
        "network-flap": [("primary_network_recovered", bool(state.get("network", {}).get("enp116s0", {}).get("link_up", False)), True)],
        "lcd-loss-recovery": [("lcd_recovered", bool(state.get("lcd", {}).get("connected", False)), True)],
        "stale-telemetry-recovery": [
            ("telemetry_entered_safe_automatic", "automatic" in recommendations, True),
            ("telemetry_recovered", bool(state.get("telemetry_fresh", False)), True),
            ("thermal_policy_recovered_from_automatic", recommendations[-1] if recommendations else None, "cooling_boost"),
        ],
    }
    return [{"check_id": check_id, "passed": actual == expected} for check_id, actual, expected in checks[name]]


def run_mission_report(name: str, *, runtime_dir: str | Path) -> dict[str, Any]:
    scenario = mission_scenario(name)
    provider = HoloDeckHostProvider(host_fixture(scenario.host), scenario=scenario)
    runner = HoloDeckScenarioRunner(provider, runtime_dir=runtime_dir)
    observation_times = _observation_schedule(scenario)
    observations = [runner.step()]
    previous_time = 0.0
    for observation_time in observation_times[1:]:
        observations.append(runner.step(observation_time - previous_time))
        previous_time = observation_time
    invariant_result = evaluate_timeline(observations)
    operator_acceptance = acceptance_payload(scenario.name, observations)
    temporal_semantics = temporal_payload(scenario.name, observations, observation_times)
    final = observations[-1]
    recommendations = [observation.recommendation.recommended_profile.value for observation in observations]
    pools = {str(pool.get("name")): str(pool.get("health", "UNKNOWN")) for pool in final.state.get("pools", []) if isinstance(pool, dict)}
    fan_events = sum(1 for observation in observations for event in observation.events if "fan" in str(getattr(event, "source", "")).lower() or "fan" in str(getattr(event, "kind", "")).lower())
    storage_events = sum(1 for observation in observations for event in observation.events if "storage" in str(getattr(event, "source", "")).lower() or "storage" in str(getattr(event, "kind", "")).lower())
    contracts = _terminal_contract(scenario.name, final.state, recommendations)
    contracts_passed = all(item["passed"] for item in contracts)
    passed = invariant_result.passed and contracts_passed and operator_acceptance["passed"] and temporal_semantics["passed"]
    return {
        "mission": scenario.name,
        "host": scenario.host,
        "passed": passed,
        "simulated_seconds": previous_time,
        "observation_interval_seconds": DEFAULT_OBSERVATION_INTERVAL_SECONDS,
        "scenario_event_count": len(scenario.events),
        "observation_count": len(observations),
        "mission_event_count": sum(len(item.events) for item in observations),
        "fan_event_count": fan_events,
        "storage_event_count": storage_events,
        "thermal_recommendations": recommendations,
        "contracts": {"passed": contracts_passed, "check_count": len(contracts), "checks": contracts},
        "mission_control_acceptance": operator_acceptance,
        "temporal_semantics": temporal_semantics,
        "invariants": {"passed": invariant_result.passed, "rule_count": invariant_result.rule_count, "violation_count": len(invariant_result.violations), "violations": [{"rule_id": item.rule_id, "observation_index": item.observation_index} for item in invariant_result.violations]},
        "final": {
            "cpu_temperature_c": final.state.get("cpu_temperature_c"),
            "telemetry_fresh": bool(final.state.get("telemetry_fresh", False)),
            "lcd_connected": bool(final.state.get("lcd", {}).get("connected", False)),
            "primary_network_up": bool(final.state.get("network", {}).get("enp116s0", {}).get("link_up", False)),
            "pool_health": pools,
        },
    }


def run_flight_deck_report(*, runtime_dir: str | Path) -> dict[str, Any]:
    root = Path(runtime_dir)
    reports = [run_mission_report(name, runtime_dir=root / name) for name in mission_names()]
    passed = all(item["passed"] for item in reports)
    return {
        "passed": passed,
        "mission_count": len(reports),
        "passed_count": sum(1 for item in reports if item["passed"]),
        "failed_count": sum(1 for item in reports if not item["passed"]),
        "simulated_seconds": sum(item["simulated_seconds"] for item in reports),
        "scenario_event_count": sum(item["scenario_event_count"] for item in reports),
        "mission_event_count": sum(item["mission_event_count"] for item in reports),
        "mission_control_acceptance_passed": sum(1 for item in reports if item["mission_control_acceptance"]["passed"]),
        "temporal_semantics_passed": sum(1 for item in reports if item["temporal_semantics"]["passed"]),
        "missions": [{
            "mission": item["mission"],
            "passed": item["passed"],
            "contracts_passed": item["contracts"]["passed"],
            "mission_control_acceptance_passed": item["mission_control_acceptance"]["passed"],
            "temporal_semantics_passed": item["temporal_semantics"]["passed"],
            "invariants_passed": item["invariants"]["passed"],
            "violation_count": item["invariants"]["violation_count"],
        } for item in reports],
    }


__all__ = ["DEFAULT_OBSERVATION_INTERVAL_SECONDS", "run_flight_deck_report", "run_mission_report"]
