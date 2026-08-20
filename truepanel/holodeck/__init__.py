"""Deterministic, hardware-isolated TruePanel Digital Twin."""

from __future__ import annotations

from importlib import import_module

_EXPORTS = {
    "AcceptanceCheck": (".acceptance", "AcceptanceCheck"),
    "DeterministicClock": (".clock", "DeterministicClock"),
    "BlackBoxHoloDeckProvider": (".replay", "BlackBoxHoloDeckProvider"),
    "HoloDeckHostProvider": (".provider", "HoloDeckHostProvider"),
    "HoloDeckObservation": (".runner", "HoloDeckObservation"),
    "HoloDeckScenarioRunner": (".runner", "HoloDeckScenarioRunner"),
    "DEFAULT_INVARIANT_RULES": (".invariants", "DEFAULT_INVARIANT_RULES"),
    "InvariantResult": (".invariants", "InvariantResult"),
    "InvariantRule": (".invariants", "InvariantRule"),
    "InvariantViolation": (".invariants", "InvariantViolation"),
    "Scenario": (".scenario", "Scenario"),
    "ScenarioEvent": (".scenario", "ScenarioEvent"),
    "SimulationSafetyError": (".provider", "SimulationSafetyError"),
    "acceptance_payload": (".acceptance", "acceptance_payload"),
    "build_holodeck_host_agent_runtime": (
        ".host_agent",
        "build_holodeck_host_agent_runtime",
    ),
    "evaluate_mission_control_acceptance": (
        ".acceptance",
        "evaluate_mission_control_acceptance",
    ),
    "evaluate_observation": (".invariants", "evaluate_observation"),
    "evaluate_timeline": (".invariants", "evaluate_timeline"),
    "load_scenario": (".scenario", "load_scenario"),
    "mission_names": (".missions", "mission_names"),
    "mission_scenario": (".missions", "mission_scenario"),
    "run_flight_deck_report": (".report", "run_flight_deck_report"),
    "run_mission_report": (".report", "run_mission_report"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as error:
        raise AttributeError(name) from error

    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
