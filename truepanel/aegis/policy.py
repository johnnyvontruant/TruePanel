"""Replaceable, declarative incident-correlation policy for AEGIS.

The policy borrows the *semantics* of label grouping and inhibition from
Prometheus Alertmanager, but contains no Alertmanager source code.  TruePanel
owns this small interface so the implementation can be replaced without
changing Mission Control or the evidence schema.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class HypothesisRule:
    """One evidence contract capable of producing a probable-cause hypothesis."""

    key: str
    likely_cause: str
    summary: str
    evidence_groups: tuple[tuple[str, ...], ...]
    evidence_weights: tuple[tuple[str, float], ...]
    group_by: tuple[str, ...]
    inhibits: tuple[str, ...]
    verification_scenario: str
    base_confidence: float = 0.45
    confidence_cap: float = 0.97


@dataclass(frozen=True)
class PolicyMatch:
    """Auditable result of one declarative hypothesis match."""

    rule: HypothesisRule
    evidence_keys: tuple[str, ...]
    matched_alerts: tuple[str, ...]
    inhibited_alerts: tuple[str, ...]
    confidence: float


class CorrelationPolicy(Protocol):
    """Narrow boundary between AEGIS composition and correlation behavior."""

    def evaluate(
        self,
        cards: Iterable[Mapping[str, Any]],
        outlook: Mapping[str, Any],
    ) -> PolicyMatch | None: ...

    def describe(self) -> dict[str, Any]: ...

    def validate(self, *, known_alerts: Iterable[str] = ()) -> tuple[str, ...]: ...


def _text(value: Any) -> str:
    return str(value or "").strip()


def _evidence_keys(
    cards: Iterable[Mapping[str, Any]],
    outlook: Mapping[str, Any],
) -> set[str]:
    keys = {
        f"signal:{_text(key)}"
        for key in outlook.get("active_signals", ())
        if _text(key)
    }
    keys.update(
        f"correlation:{_text(item.get('key'))}"
        for item in outlook.get("correlations", ())
        if isinstance(item, Mapping) and _text(item.get("key"))
    )
    keys.update(
        f"alert:{_text(card.get('code'))}"
        for card in cards
        if _text(card.get("code"))
    )
    return keys


class DeclarativeCorrelationPolicy:
    """Match hypotheses only when every independent evidence group is present."""

    def __init__(self, rules: Iterable[HypothesisRule]) -> None:
        self.rules = tuple(rules)

    def evaluate(
        self,
        cards: Iterable[Mapping[str, Any]],
        outlook: Mapping[str, Any],
    ) -> PolicyMatch | None:
        card_list = tuple(cards)
        available = _evidence_keys(card_list, outlook)
        matches = []
        for rule in self.rules:
            if not all(available.intersection(group) for group in rule.evidence_groups):
                continue
            weights = dict(rule.evidence_weights)
            matched = tuple(sorted(available.intersection(weights)))
            confidence = min(
                rule.confidence_cap,
                rule.base_confidence + sum(weights[key] for key in matched),
            )
            alerts = tuple(
                sorted(key.removeprefix("alert:") for key in matched if key.startswith("alert:"))
            )
            inhibited = tuple(code for code in rule.inhibits if code in alerts)
            matches.append(
                PolicyMatch(
                    rule=rule,
                    evidence_keys=matched,
                    matched_alerts=alerts,
                    inhibited_alerts=inhibited,
                    confidence=round(confidence, 2),
                )
            )
        if not matches:
            return None
        return max(matches, key=lambda item: (item.confidence, item.rule.key))

    def describe(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "policy_id": "aegis-declarative-correlation-v1",
            "semantics": "evidence grouping with non-destructive inhibition",
            "replaceable": True,
            "rule_count": len(self.rules),
            "verification_scenarios": [rule.verification_scenario for rule in self.rules],
            "provenance": {
                "project": "Prometheus Alertmanager",
                "license": "Apache-2.0",
                "use": "architectural adaptation; no source code copied",
            },
        }

    def validate(self, *, known_alerts: Iterable[str] = ()) -> tuple[str, ...]:
        errors = []
        known = set(known_alerts)
        seen = set()
        for rule in self.rules:
            prefix = rule.key or "<unnamed>"
            if not rule.key or rule.key in seen:
                errors.append(f"{prefix}: rule key must be present and unique")
            seen.add(rule.key)
            if len(rule.evidence_groups) < 2 or any(not group for group in rule.evidence_groups):
                errors.append(f"{prefix}: at least two non-empty evidence groups are required")
            if not rule.group_by:
                errors.append(f"{prefix}: presentation grouping is not declared")
            if not rule.verification_scenario:
                errors.append(f"{prefix}: deterministic verification scenario is missing")
            if not 0 <= rule.base_confidence < rule.confidence_cap <= 0.99:
                errors.append(f"{prefix}: confidence bounds are invalid")
            weights = dict(rule.evidence_weights)
            if len(weights) != len(rule.evidence_weights) or any(
                not 0 < weight <= 1 for weight in weights.values()
            ):
                errors.append(f"{prefix}: evidence weights must be unique and in (0, 1]")
            declared = {key for group in rule.evidence_groups for key in group}
            if not declared.issubset(weights):
                errors.append(f"{prefix}: every evidence key requires an explicit weight")
            if any(
                not key.startswith(("signal:", "correlation:", "alert:"))
                for key in weights
            ):
                errors.append(f"{prefix}: evidence keys must declare their source namespace")
            if known and not set(rule.inhibits).issubset(known):
                errors.append(f"{prefix}: inhibited alert is not in the guidance catalog")
        return tuple(errors)


SHARED_COOLING_RULE = HypothesisRule(
    key="shared-cooling",
    likely_cause="Shared chassis cooling degradation",
    summary=(
        "Fan delivery, cooling effort, and temperature evidence point to one "
        "shared airflow cause rather than independent fan and thermal incidents."
    ),
    evidence_groups=(
        ("signal:fan.rpm", "alert:cooling.fan_stall"),
        (
            "signal:fan.pwm",
            "signal:drive.temperature_c",
            "signal:cpu.temperature_c",
            "correlation:cooling.efficiency",
            "correlation:chassis.airflow",
            "alert:thermal.high_temperature",
        ),
    ),
    evidence_weights=(
        ("signal:fan.rpm", 0.14),
        ("signal:fan.pwm", 0.12),
        ("signal:drive.temperature_c", 0.08),
        ("signal:cpu.temperature_c", 0.06),
        ("correlation:cooling.efficiency", 0.12),
        ("correlation:chassis.airflow", 0.10),
        ("alert:cooling.fan_stall", 0.20),
        ("alert:thermal.high_temperature", 0.16),
    ),
    group_by=("physical_domain", "probable_cause"),
    inhibits=("thermal.high_temperature",),
    verification_scenario="aegis-correlation-calibration-v1",
)

DEFAULT_CORRELATION_POLICY = DeclarativeCorrelationPolicy((SHARED_COOLING_RULE,))


def validate_correlation_policy() -> tuple[str, ...]:
    """Return CI contract violations for the built-in correlation policy."""

    from truepanel.guidance.catalog import guidance_codes

    return DEFAULT_CORRELATION_POLICY.validate(known_alerts=guidance_codes())


__all__ = [
    "CorrelationPolicy",
    "DEFAULT_CORRELATION_POLICY",
    "DeclarativeCorrelationPolicy",
    "HypothesisRule",
    "PolicyMatch",
    "validate_correlation_policy",
]
