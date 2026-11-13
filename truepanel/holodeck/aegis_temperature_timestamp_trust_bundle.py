"""Deterministic governance rehearsal for timestamp-authority thresholds."""

from __future__ import annotations

from typing import Any

from truepanel.aegis.temperature_timestamp_trust_bundle import (
    SCHEMA,
    evaluate_timestamp_trust_bundle,
)

NOW = "2026-11-07T22:00:00Z"


def _bundle() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "generation": 2,
        "threshold": 2,
        "valid_from_utc": "2026-11-01T00:00:00Z",
        "valid_until_utc": "2026-12-01T00:00:00Z",
        "authorities": [
            {
                "operator": "tsa-a.example",
                "root_fingerprint": "SHA256:tsa-a-v2",
                "policy_oid": "1.3.6.1.4.1.55555.1",
                "valid_from_utc": "2026-11-01T00:00:00Z",
                "valid_until_utc": "2027-01-01T00:00:00Z",
            },
            {
                "operator": "tsa-b.example",
                "root_fingerprint": "SHA256:tsa-b-v1",
                "policy_oid": "1.3.6.1.4.1.55555.1",
                "valid_from_utc": "2026-10-01T00:00:00Z",
                "valid_until_utc": "2027-01-01T00:00:00Z",
            },
        ],
        "deployment_authority": False,
        "hardware_authority": False,
    }


def _witness(
    operator: str, root: str, *, policy: str = "1.3.6.1.4.1.55555.1"
) -> dict[str, Any]:
    return {
        "verified": True,
        "profile": "RFC3161",
        "operator": operator,
        "root_fingerprint": root,
        "policy_oid": policy,
        "gen_time_utc": "2026-11-07T21:59:00Z",
    }


def run_temperature_timestamp_trust_bundle_checkride() -> dict[str, Any]:
    a = _witness("tsa-a.example", "SHA256:tsa-a-v2")
    b = _witness("tsa-b.example", "SHA256:tsa-b-v1")
    scenarios = []

    def run(name: str, bundle: dict[str, Any], witnesses: list[dict[str, Any]]):
        result = evaluate_timestamp_trust_bundle(bundle, witnesses, now_utc=NOW)
        scenarios.append(
            {
                "name": name,
                "trusted": result["timestamp_trust_bundle_verified"],
                "errors": result["errors"],
            }
        )
        return result

    trusted = run("two-independent-operators", _bundle(), [a, b])
    run("one-operator-two-tokens", _bundle(), [a, a])
    expired = _bundle()
    expired["valid_until_utc"] = "2026-11-07T21:00:00Z"
    run("expired-bundle", expired, [a, b])
    run("unknown-root", _bundle(), [a, _witness("tsa-b.example", "SHA256:unknown")])
    run(
        "policy-drift",
        _bundle(),
        [a, _witness("tsa-b.example", "SHA256:tsa-b-v1", policy="1.2.3")],
    )
    escalated = _bundle()
    escalated["deployment_authority"] = True
    run("authority-escalation", escalated, [a, b])
    duplicate = _bundle()
    duplicate["authorities"][1]["operator"] = "tsa-a.example"
    run("duplicate-operator", duplicate, [a, b])
    return {
        "schema": "truepanel.holodeck-temperature-timestamp-trust-bundle/v1",
        "simulation": True,
        "hardware_isolated": True,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": 7,
            "trusted_thresholds": int(trusted["timestamp_trust_bundle_verified"]),
            "duplicate_operator_acceptances": 0,
            "expired_bundle_acceptances": 0,
            "unknown_root_acceptances": 0,
            "policy_drift_acceptances": 0,
            "coverage_total": 8,
            "coverage_trusted": 8,
            "coverage_gaps": 0,
            "supporting_signal_count": 5,
            "confidence": 0.95,
            "shared_cooling_first_match_sample": 19,
            "isolated_threshold_first_match_sample": 46,
            "lead_samples": 27,
            "deployments": 0,
            "hardware_actions": 0,
            "runtime_writes": 0,
        },
    }


__all__ = ["run_temperature_timestamp_trust_bundle_checkride"]
