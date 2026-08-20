"""Operator-visible acceptance contracts for HoloDeck mission timelines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .runner import HoloDeckObservation


@dataclass(frozen=True)
class AcceptanceCheck:
    """One privacy-safe Mission Control acceptance result."""

    check_id: str
    passed: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "passed": self.passed,
        }


def _subsystem_states(
    observations: Iterable[HoloDeckObservation],
    subsystem: str,
) -> list[str]:
    states = []
    for observation in observations:
        health = observation.snapshot.get("health", {})
        subsystems = health.get("subsystems", {})
        payload = subsystems.get(subsystem, {})
        states.append(str(payload.get("state", "UNKNOWN")))
    return states


def _thermal_profiles(
    observations: Iterable[HoloDeckObservation],
) -> list[str]:
    profiles = []
    for observation in observations:
        control = observation.snapshot.get("fans", {}).get("control", {})
        profiles.append(
            str(control.get("thermal_recommended_profile", "automatic"))
        )
    return profiles


def _thermal_validity(
    observations: Iterable[HoloDeckObservation],
) -> list[bool]:
    values = []
    for observation in observations:
        control = observation.snapshot.get("fans", {}).get("control", {})
        values.append(bool(control.get("thermal_telemetry_valid", False)))
    return values


def _check(check_id: str, condition: bool) -> AcceptanceCheck:
    return AcceptanceCheck(check_id=check_id, passed=bool(condition))


def evaluate_mission_control_acceptance(
    mission: str,
    observations: Iterable[HoloDeckObservation],
) -> tuple[AcceptanceCheck, ...]:
    """Verify that Mission Control exposes the incident and recovery correctly."""

    timeline = tuple(observations)
    if not timeline:
        return (_check("mission_control.timeline_present", False),)

    checks: list[AcceptanceCheck] = [
        _check(
            "mission_control.snapshot_read_only",
            all(item.snapshot.get("read_only") is True for item in timeline),
        ),
        _check(
            "mission_control.health_present",
            all(isinstance(item.snapshot.get("health"), dict) for item in timeline),
        ),
    ]

    if mission == "thermal-ramp":
        profiles = _thermal_profiles(timeline)
        checks.extend(
            [
                _check(
                    "mission_control.thermal_afterburners_visible",
                    "afterburners" in profiles,
                ),
                _check(
                    "mission_control.thermal_downshift_visible",
                    profiles[-1] == "cooling_boost",
                ),
                _check(
                    "mission_control.thermal_recommendation_matches_policy",
                    profiles
                    == [
                        item.recommendation.recommended_profile.value
                        for item in timeline
                    ],
                ),
            ]
        )
    elif mission == "fan-stall-recovery":
        states = _subsystem_states(timeline, "cooling")
        checks.extend(
            [
                _check(
                    "mission_control.cooling_degraded_visible",
                    "DEGRADED" in states,
                ),
                _check(
                    "mission_control.cooling_recovery_visible",
                    states[-1] == "NOMINAL",
                ),
            ]
        )
    elif mission in {"drive-failure", "drive-removal"}:
        states = _subsystem_states(timeline, "storage")
        checks.extend(
            [
                _check(
                    "mission_control.storage_degraded_visible",
                    "DEGRADED" in states,
                ),
                _check(
                    "mission_control.storage_terminal_degraded",
                    states[-1] == "DEGRADED",
                ),
            ]
        )
    elif mission == "network-flap":
        states = _subsystem_states(timeline, "network")
        checks.extend(
            [
                _check(
                    "mission_control.network_degraded_visible",
                    "DEGRADED" in states,
                ),
                _check(
                    "mission_control.network_recovery_visible",
                    states[-1] == "NOMINAL",
                ),
            ]
        )
    elif mission == "lcd-loss-recovery":
        states = _subsystem_states(timeline, "front_panel")
        checks.extend(
            [
                _check(
                    "mission_control.front_panel_degraded_visible",
                    "DEGRADED" in states,
                ),
                _check(
                    "mission_control.front_panel_recovery_visible",
                    states[-1] == "NOMINAL",
                ),
            ]
        )
    elif mission == "stale-telemetry-recovery":
        profiles = _thermal_profiles(timeline)
        validity = _thermal_validity(timeline)
        checks.extend(
            [
                _check(
                    "mission_control.stale_thermal_invalid_visible",
                    False in validity,
                ),
                _check(
                    "mission_control.stale_thermal_automatic_visible",
                    "automatic" in profiles,
                ),
                _check(
                    "mission_control.thermal_validity_recovered",
                    validity[-1] is True,
                ),
                _check(
                    "mission_control.thermal_profile_recovered",
                    profiles[-1] == "cooling_boost",
                ),
            ]
        )
    else:
        checks.append(_check("mission_control.known_mission", False))

    return tuple(checks)


def acceptance_payload(
    mission: str,
    observations: Iterable[HoloDeckObservation],
) -> dict[str, Any]:
    """Return a compact acceptance summary without raw Mission Control state."""

    checks = evaluate_mission_control_acceptance(mission, observations)
    return {
        "passed": all(item.passed for item in checks),
        "check_count": len(checks),
        "failed_count": sum(not item.passed for item in checks),
        "checks": [item.as_dict() for item in checks],
    }


__all__ = [
    "AcceptanceCheck",
    "acceptance_payload",
    "evaluate_mission_control_acceptance",
]
