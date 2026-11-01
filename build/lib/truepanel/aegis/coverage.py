"""Universal Recovery Coverage Matrix and its CI-enforceable contract."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from truepanel.guidance.catalog import guidance_codes, guidance_for
from truepanel.guidance.recovery import verification_for_card


@dataclass(frozen=True)
class CoverageDefinition:
    detector: str
    regression_scenarios: tuple[str, ...]
    recovery_owner: str = "Pathfinder"
    diagnosis_owner: str = "Operator Guidance"


_COVERAGE: dict[str, CoverageDefinition] = {
    "cooling.fan_stall": CoverageDefinition(
        "FanHealthWatcher debounced monitored-channel alarm",
        ("fan-stall-recovery", "aegis-shared-cooling-degradation"),
    ),
    "thermal.high_temperature": CoverageDefinition(
        "Evidence-bound upstream thermal alarm",
        ("thermal-ramp", "aegis-shared-cooling-degradation"),
    ),
    "storage.smart_warning": CoverageDefinition(
        "SMART evidence correlated to verified ZFS membership",
        ("oracle-drive-slow-degradation",),
        recovery_owner="Pathfinder + Lifeline",
    ),
    "storage.disk_faulted": CoverageDefinition(
        "StorageHealthWatcher and verified member evidence",
        ("drive-failure", "drive-failure-recovery"),
        recovery_owner="Pathfinder + Lifeline",
    ),
    "storage.pool_degraded": CoverageDefinition(
        "ZFS pool-state collector",
        ("drive-failure-recovery", "drive-removal-reinsert"),
        recovery_owner="Pathfinder + Lifeline",
    ),
    "network.link_down": CoverageDefinition(
        "Verified primary-interface link state",
        ("network-flap",),
    ),
    "front_panel.lcd_unavailable": CoverageDefinition(
        "LCD reader/display status bridges",
        ("lcd-loss-recovery",),
    ),
    "telemetry.stale": CoverageDefinition(
        "Host Agent freshness and missing-domain contract",
        ("stale-telemetry-recovery",),
    ),
}


def _verification_probe(code: str) -> dict[str, Any]:
    card = {
        "code": code,
        "runtime": {"evidence": {}},
    }
    return verification_for_card(card)


def validate_recovery_coverage() -> tuple[str, ...]:
    """Return contract violations; an empty tuple is the CI PASS condition."""

    errors: list[str] = []
    catalog_codes = set(guidance_codes())
    definition_codes = set(_COVERAGE)

    for code in sorted(catalog_codes - definition_codes):
        errors.append(f"{code}: missing recovery coverage definition")
    for code in sorted(definition_codes - catalog_codes):
        errors.append(f"{code}: coverage definition has no guidance catalog entry")

    for code in guidance_codes():
        definition = _COVERAGE.get(code)
        if definition is None:
            continue
        guidance = guidance_for(code)
        if not definition.detector.strip():
            errors.append(f"{code}: detector is not declared")
        if not guidance.evidence_fields:
            errors.append(f"{code}: diagnosis has no evidence fields")
        for section in (
            "immediate_actions",
            "diagnosis",
            "remediation",
            "verification",
        ):
            if not getattr(guidance, section):
                errors.append(f"{code}: guidance section {section} is empty")
        verifier = _verification_probe(code)
        if verifier.get("automated") is not True:
            errors.append(f"{code}: verification is not machine-verifiable")
        if verifier.get("strategy") == "operator_and_telemetry_recheck":
            errors.append(f"{code}: verification uses the generic fallback")
        if not definition.regression_scenarios:
            errors.append(f"{code}: no deterministic regression scenario")

    return tuple(errors)


def coverage_matrix(
    rehearsal_evidence: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the operator-facing matrix without granting repair authority."""

    rehearsal_evidence = rehearsal_evidence or {}
    contract_errors = validate_recovery_coverage()
    entries = []
    for code in guidance_codes():
        definition = _COVERAGE.get(code)
        guidance = guidance_for(code)
        verifier = _verification_probe(code)
        rehearsal = dict(rehearsal_evidence.get(code, {}))
        gaps = [
            error.split(": ", 1)[1]
            for error in contract_errors
            if error.startswith(f"{code}:")
        ]
        if rehearsal.get("status") != "passed":
            gaps.append("safe verification rehearsal has not passed")
        trusted = not gaps
        entries.append(
            {
                "code": code,
                "title": guidance.title,
                "severity": guidance.severity,
                **(asdict(definition) if definition else {}),
                "diagnostic_evidence": list(guidance.evidence_fields),
                "actionable_guidance": bool(
                    guidance.immediate_actions
                    and guidance.diagnosis
                    and guidance.remediation
                ),
                "verification": {
                    "strategy": verifier.get("strategy"),
                    "machine_verifiable": verifier.get("automated") is True,
                    "criteria": verifier.get("criteria"),
                },
                "rehearsal": rehearsal,
                "coverage_state": "TRUSTED" if trusted else "GAP",
                "gaps": gaps,
            }
        )

    trusted_count = sum(item["coverage_state"] == "TRUSTED" for item in entries)
    return {
        "schema_version": 1,
        "read_only": True,
        "contract": "actionable alerts require guidance, verification, and simulation",
        "total": len(entries),
        "trusted": trusted_count,
        "gaps": len(entries) - trusted_count,
        "contract_errors": list(contract_errors),
        "entries": entries,
    }


__all__ = ["coverage_matrix", "validate_recovery_coverage"]
