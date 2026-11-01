"""Pure, deterministic safety rules for HoloDeck observations."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

Evidence = tuple[tuple[str, str], ...]
RuleCheck = Callable[[Any], Evidence | None]


def _text(value: Any) -> str:
    """Return a stable, compact representation for violation evidence."""

    if isinstance(value, Enum):
        value = value.value
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _evidence(**values: Any) -> Evidence:
    return tuple(sorted((key, _text(value)) for key, value in values.items()))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _part(observation: Any, name: str) -> Any:
    if isinstance(observation, Mapping):
        return observation.get(name)
    return getattr(observation, name, None)


def _state(observation: Any) -> Mapping[str, Any]:
    state = _part(observation, "state")
    if isinstance(state, Mapping):
        return state
    return observation if isinstance(observation, Mapping) else {}


def _snapshot(observation: Any) -> Mapping[str, Any]:
    return _mapping(_part(observation, "snapshot"))


def _profile(observation: Any) -> str:
    recommendation = _part(observation, "recommendation")
    profile = getattr(recommendation, "recommended_profile", None)
    if profile is None and isinstance(recommendation, Mapping):
        profile = recommendation.get("recommended_profile")
    if isinstance(profile, Enum):
        profile = profile.value
    return str(profile or "").lower()


@dataclass(frozen=True)
class InvariantRule:
    """A named, side-effect-free predicate over one observation."""

    rule_id: str
    description: str
    check: RuleCheck

    def __post_init__(self) -> None:
        if not self.rule_id or not self.rule_id.strip():
            raise ValueError("invariant rule_id cannot be empty")
        if not callable(self.check):
            raise TypeError("invariant check must be callable")


@dataclass(frozen=True)
class InvariantViolation:
    """Deterministic evidence that one rule failed at one timeline position."""

    rule_id: str
    description: str
    observation_index: int
    evidence: Evidence


@dataclass(frozen=True)
class InvariantResult:
    """Complete result of evaluating rules against a timeline."""

    observation_count: int
    rule_count: int
    violations: tuple[InvariantViolation, ...]

    @property
    def passed(self) -> bool:
        return not self.violations

    def violations_for(self, rule_id: str) -> tuple[InvariantViolation, ...]:
        return tuple(item for item in self.violations if item.rule_id == rule_id)


def _hardware_isolated(observation: Any) -> Evidence | None:
    state = _state(observation)
    if state.get("simulation") is True and state.get("read_only") is True:
        return None
    return _evidence(
        simulation=state.get("simulation"),
        read_only=state.get("read_only"),
    )


def _stale_telemetry_is_automatic(observation: Any) -> Evidence | None:
    fresh = _state(observation).get("telemetry_fresh")
    if fresh is not False:
        return None
    profile = _profile(observation)
    if profile == "automatic":
        return None
    return _evidence(telemetry_fresh=fresh, recommended_profile=profile or None)


def _stalled_fan_not_healthy(observation: Any) -> Evidence | None:
    fans = _mapping(_state(observation).get("fans"))
    channels = fans.get("fan_channels", fans.get("channels", ()))
    if not isinstance(channels, (list, tuple)):
        return None
    offenders: list[str] = []
    for index, value in enumerate(channels):
        channel = _mapping(value)
        stalled = channel.get("stalled") is True or channel.get("rpm") == 0
        healthy = channel.get("healthy") is True
        alarm_missing = channel.get("alarm") is False
        if stalled and (healthy or alarm_missing):
            offenders.append(str(channel.get("number", index + 1)))
    if not offenders and not (
        fans.get("rpm") == 0 and fans.get("healthy") is True
    ):
        return None
    return _evidence(stalled_channels=",".join(offenders) or "aggregate", healthy=True)


def _degraded_pool_not_nominal(observation: Any) -> Evidence | None:
    pools = _state(observation).get("pools", ())
    if not isinstance(pools, (list, tuple)):
        return None
    degraded = sorted(
        str(pool.get("name", index))
        for index, pool in enumerate(pools)
        if isinstance(pool, Mapping)
        and str(pool.get("health", "UNKNOWN")).upper() not in {"ONLINE", "HEALTHY"}
    )
    if not degraded:
        return None
    health = _mapping(_snapshot(observation).get("health"))
    subsystems = _mapping(health.get("subsystems"))
    storage_state = str(_mapping(subsystems.get("storage")).get("state", "UNKNOWN")).upper()
    if storage_state != "NOMINAL":
        return None
    return _evidence(degraded_pools=",".join(degraded), storage_state=storage_state)


DEFAULT_INVARIANT_RULES = (
    InvariantRule(
        "holodeck.hardware_isolated",
        "HoloDeck state remains simulation-only and read-only",
        _hardware_isolated,
    ),
    InvariantRule(
        "thermal.stale_is_automatic",
        "Stale telemetry recommends the fail-safe Automatic profile",
        _stale_telemetry_is_automatic,
    ),
    InvariantRule(
        "cooling.stalled_not_healthy",
        "A stalled fan is never represented as healthy",
        _stalled_fan_not_healthy,
    ),
    InvariantRule(
        "storage.degraded_not_nominal",
        "A degraded pool is never reported as nominal",
        _degraded_pool_not_nominal,
    ),
)


def evaluate_timeline(
    observations: Iterable[Any],
    rules: Iterable[InvariantRule] = DEFAULT_INVARIANT_RULES,
) -> InvariantResult:
    """Evaluate all rules in stable rule-major, observation-minor order."""

    timeline = tuple(observations)
    selected_rules = tuple(rules)
    violations: list[InvariantViolation] = []
    for rule in selected_rules:
        if not isinstance(rule, InvariantRule):
            raise TypeError("rules must contain InvariantRule values")
        for index, observation in enumerate(timeline):
            evidence = rule.check(observation)
            if evidence is not None:
                violations.append(
                    InvariantViolation(
                        rule_id=rule.rule_id,
                        description=rule.description,
                        observation_index=index,
                        evidence=tuple(evidence),
                    )
                )
    return InvariantResult(
        observation_count=len(timeline),
        rule_count=len(selected_rules),
        violations=tuple(violations),
    )


def evaluate_observation(
    observation: Any,
    rules: Iterable[InvariantRule] = DEFAULT_INVARIANT_RULES,
) -> InvariantResult:
    """Evaluate one observation using the same semantics as a timeline."""

    return evaluate_timeline((observation,), rules)


__all__ = [
    "DEFAULT_INVARIANT_RULES",
    "Evidence",
    "InvariantResult",
    "InvariantRule",
    "InvariantViolation",
    "evaluate_observation",
    "evaluate_timeline",
]
