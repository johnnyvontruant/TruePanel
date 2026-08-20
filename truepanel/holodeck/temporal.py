"""Temporal behavior contracts for deterministic HoloDeck missions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from .runner import HoloDeckObservation


@dataclass(frozen=True)
class TemporalCheck:
    """One privacy-safe timing or transition contract."""

    check_id: str
    passed: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "passed": self.passed,
        }


def _check(check_id: str, condition: bool) -> TemporalCheck:
    return TemporalCheck(check_id=check_id, passed=bool(condition))


def _event_times(
    observations: Sequence[HoloDeckObservation],
    observation_times: Sequence[float],
    *,
    source: str | None = None,
    event_id: str | None = None,
    change_type: str | None = None,
) -> list[float]:
    matches: list[float] = []
    for at, observation in zip(observation_times, observations):
        for event in observation.events:
            if source is not None and event.source != source:
                continue
            if event_id is not None and event.event_id != event_id:
                continue
            if change_type is not None and event.metadata.get("change_type") != change_type:
                continue
            matches.append(float(at))
    return matches


def _subsystem_states(
    observations: Sequence[HoloDeckObservation],
    subsystem: str,
) -> list[str]:
    states: list[str] = []
    for observation in observations:
        payload = (
            observation.snapshot.get("health", {})
            .get("subsystems", {})
            .get(subsystem, {})
        )
        states.append(str(payload.get("state", "UNKNOWN")))
    return states


def _thermal_validity(
    observations: Sequence[HoloDeckObservation],
) -> list[bool]:
    return [
        bool(
            observation.snapshot.get("fans", {})
            .get("control", {})
            .get("thermal_telemetry_valid", False)
        )
        for observation in observations
    ]


def _states_between(
    observation_times: Sequence[float],
    states: Sequence[Any],
    *,
    start: float,
    end: float,
) -> list[Any]:
    return [
        state
        for at, state in zip(observation_times, states)
        if start <= float(at) < end
    ]


def evaluate_temporal_contracts(
    mission: str,
    observations: Iterable[HoloDeckObservation],
    observation_times: Iterable[float],
) -> tuple[TemporalCheck, ...]:
    """Verify debounce, persistence, recovery, and duplicate suppression."""

    timeline = tuple(observations)
    times = tuple(float(value) for value in observation_times)
    if not timeline or len(timeline) != len(times):
        return (_check("temporal.timeline_aligned", False),)

    checks: list[TemporalCheck] = [
        _check("temporal.timeline_aligned", len(timeline) == len(times)),
        _check("temporal.timeline_starts_at_zero", times[0] == 0.0),
        _check(
            "temporal.timeline_monotonic",
            all(later > earlier for earlier, later in zip(times, times[1:])),
        ),
    ]

    if mission == "fan-stall-recovery":
        warning_times = _event_times(
            timeline,
            times,
            source="fan_health_watcher",
            event_id="thermal.fan1.low_rpm",
        )
        recovery_times = _event_times(
            timeline,
            times,
            source="fan_health_watcher",
            event_id="thermal.fan1.recovered",
        )
        checks.extend(
            [
                _check(
                    "temporal.fan_debounce_observations_present",
                    all(value in times for value in (30.0, 40.0, 50.0)),
                ),
                _check(
                    "temporal.fan_alert_on_third_failed_observation",
                    warning_times == [50.0],
                ),
                _check(
                    "temporal.fan_alert_not_duplicated",
                    len(warning_times) == 1,
                ),
                _check(
                    "temporal.fan_recovery_emitted_once",
                    recovery_times == [120.0],
                ),
            ]
        )
    elif mission == "drive-failure":
        degraded_times = _event_times(
            timeline,
            times,
            source="storage_health_watcher",
            change_type="health_degraded",
        )
        checks.extend(
            [
                _check(
                    "temporal.storage_fault_transition_once",
                    degraded_times == [30.0],
                ),
                _check(
                    "temporal.storage_fault_not_duplicated",
                    len(degraded_times) == 1,
                ),
            ]
        )
    elif mission == "drive-removal":
        missing_times = _event_times(
            timeline,
            times,
            source="storage_health_watcher",
            change_type="device_missing",
        )
        checks.extend(
            [
                _check(
                    "temporal.storage_removal_transition_once",
                    missing_times == [30.0],
                ),
                _check(
                    "temporal.storage_removal_not_duplicated",
                    len(missing_times) == 1,
                ),
            ]
        )
    elif mission == "network-flap":
        states = _subsystem_states(timeline, "network")
        outage_states = _states_between(times, states, start=30.0, end=90.0)
        checks.extend(
            [
                _check(
                    "temporal.network_outage_persists",
                    bool(outage_states)
                    and all(state == "DEGRADED" for state in outage_states),
                ),
                _check(
                    "temporal.network_recovers_at_event",
                    next(
                        (state for at, state in zip(times, states) if at == 90.0),
                        None,
                    )
                    == "NOMINAL",
                ),
            ]
        )
    elif mission == "lcd-loss-recovery":
        states = _subsystem_states(timeline, "front_panel")
        outage_states = _states_between(times, states, start=30.0, end=90.0)
        checks.extend(
            [
                _check(
                    "temporal.front_panel_outage_persists",
                    bool(outage_states)
                    and all(state == "DEGRADED" for state in outage_states),
                ),
                _check(
                    "temporal.front_panel_recovers_at_event",
                    next(
                        (state for at, state in zip(times, states) if at == 90.0),
                        None,
                    )
                    == "NOMINAL",
                ),
            ]
        )
    elif mission == "stale-telemetry-recovery":
        validity = _thermal_validity(timeline)
        stale_values = _states_between(times, validity, start=30.0, end=120.0)
        checks.extend(
            [
                _check(
                    "temporal.stale_telemetry_persists",
                    bool(stale_values) and all(value is False for value in stale_values),
                ),
                _check(
                    "temporal.telemetry_recovers_at_event",
                    next(
                        (value for at, value in zip(times, validity) if at == 120.0),
                        None,
                    )
                    is True,
                ),
            ]
        )
    elif mission == "thermal-ramp":
        checks.append(
            _check(
                "temporal.thermal_cadence_present",
                all(value in times for value in range(10, 301, 10)),
            )
        )

    return tuple(checks)


def temporal_payload(
    mission: str,
    observations: Iterable[HoloDeckObservation],
    observation_times: Iterable[float],
) -> dict[str, Any]:
    """Return compact temporal semantics without raw snapshots."""

    checks = evaluate_temporal_contracts(mission, observations, observation_times)
    return {
        "passed": all(item.passed for item in checks),
        "check_count": len(checks),
        "failed_count": sum(not item.passed for item in checks),
        "checks": [item.as_dict() for item in checks],
    }


__all__ = [
    "TemporalCheck",
    "evaluate_temporal_contracts",
    "temporal_payload",
]
