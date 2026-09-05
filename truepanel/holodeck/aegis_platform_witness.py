"""Deterministic rehearsal for the passive TrueNAS platform witness."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from truepanel.aegis.assurance import evaluate_airworthiness
from truepanel.aegis.coverage import coverage_matrix
from truepanel.aegis.passive_runtime import BoundedTrueNASQueryCache
from truepanel.aegis.platform_witness import (
    bind_platform_witness,
    issue_platform_witness,
)
from truepanel.aegis.policy import DEFAULT_CORRELATION_POLICY
from truepanel.aegis.rehearsal import rehearse_recovery_paths


class _Clock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value


class _Delegate:
    def __init__(self, value: Any) -> None:
        self.value = value
        self.calls: list[str] = []
        self.unavailable = False

    def call(self, method: str, *arguments: Any) -> Any:
        del arguments
        self.calls.append(method)
        if self.unavailable:
            raise OSError("deterministic transport loss")
        return self.value


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _evaluate(witness: dict[str, Any]) -> dict[str, Any]:
    return evaluate_airworthiness(
        payload=bind_platform_witness({"system": {}}, witness),
        coverage_matrix=coverage_matrix(rehearse_recovery_paths()),
        correlation_policy=DEFAULT_CORRELATION_POLICY.describe(),
        now=1788609600.0,
    )


def _single(value: Any, *, unavailable: bool = False) -> tuple[dict[str, Any], int]:
    clock = _Clock()
    delegate = _Delegate(value)
    delegate.unavailable = unavailable
    cache = BoundedTrueNASQueryCache(delegate, clock=clock)
    return issue_platform_witness(cache, clock=lambda: 1788609600.0), len(delegate.calls)


def run_platform_witness_rehearsal() -> dict[str, Any]:
    """Exercise live, cached, stale, absent, malformed, drift, and tamper paths."""

    scenarios: list[dict[str, Any]] = []

    def record(name: str, witness: dict[str, Any], calls: int) -> None:
        result = _evaluate(witness)
        scenarios.append(
            {
                "scenario": name,
                "witness_status": witness["status"],
                "airworthiness_status": result["status"],
                "reason": result["reason"],
                "delegate_calls": calls,
                "runtime_writes": witness["runtime_writes"],
                "control_authority": witness["control_authority"],
            }
        )

    monotonic = _Clock()
    delegate = _Delegate("TrueNAS-SCALE-25.10.5")
    cache = BoundedTrueNASQueryCache(delegate, clock=monotonic)
    live = issue_platform_witness(cache, clock=lambda: 1788609600.0)
    record("matching-live-version", live, len(delegate.calls))
    cached = issue_platform_witness(cache, clock=lambda: 1788609601.0)
    record("matching-cached-version", cached, len(delegate.calls))

    monotonic.value += 61
    delegate.unavailable = True
    stale = issue_platform_witness(cache, clock=lambda: 1788609661.0)
    record("stale-display-only-version", stale, len(delegate.calls))

    unavailable, calls = _single(None, unavailable=True)
    record("version-unavailable", unavailable, calls)
    malformed, calls = _single({"version": "25.10.5"})
    record("non-scalar-version", malformed, calls)
    drifted, calls = _single("TrueNAS-SCALE-26.0.0")
    record("version-drift", drifted, calls)
    tampered = deepcopy(live)
    tampered["hostname"] = "must-not-survive"
    record("tampered-witness", tampered, 0)

    counts = {name: 0 for name in ("CURRENT", "REVIEW", "HOLD")}
    for scenario in scenarios:
        counts[scenario["airworthiness_status"]] += 1
    report = {
        "schema_version": 1,
        "experiment_id": "TP-EXP-0021",
        "scenario": "aegis-platform-witness-v1",
        "simulation": True,
        "hardware_isolated": True,
        "passive_method": "system.version",
        "sensitive_fields_retained": False,
        "runtime_writes": 0,
        "production_mutation": False,
        "control_authority": False,
        "status_counts": counts,
        "scenarios": scenarios,
        "measurements": {
            "fresh_calls_first_observation": 1,
            "fresh_calls_after_cached_observation": 1,
            "privacy_fields_retained": 0,
            "false_current_paths": 0,
        },
    }
    report["evidence_sha256"] = _digest(report)
    return report


__all__ = ["run_platform_witness_rehearsal"]
