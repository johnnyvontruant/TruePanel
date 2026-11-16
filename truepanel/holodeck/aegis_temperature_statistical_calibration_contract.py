"""Adversarial proof for the predeclared temperature calibration policy."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable
from typing import Any

from truepanel.aegis.temperature_statistical_calibration_contract import (
    STATUS_READY,
    build_temperature_statistical_calibration_contract,
    validate_temperature_statistical_calibration_contract,
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def run_temperature_statistical_calibration_contract_checkride() -> dict[str, Any]:
    """Prove policy and cohort floors are fixed before labels are available."""

    base = build_temperature_statistical_calibration_contract(
        declared_at_utc="2026-10-22T04:30:00Z"
    )
    scenarios: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    def scenario(
        name: str, mutate: Callable[[dict[str, Any]], None] | None = None
    ) -> None:
        contract = copy.deepcopy(base)
        if mutate:
            mutate(contract)
        result = validate_temperature_statistical_calibration_contract(contract)
        results.append(result)
        scenarios.append(
            {
                "scenario": name,
                "status": result["status"],
                "contract_locked": result["contract_locked"],
                "error_count": len(result["errors"]),
            }
        )

    scenario("fixed-policy-before-labels")
    scenario(
        "positive-floor-relaxed",
        lambda item: item["policy"].update({"minimum_positive_cases": 4}),
    )
    scenario(
        "negative-floor-relaxed",
        lambda item: item["policy"].update({"minimum_negative_cases": 20}),
    )
    scenario(
        "sensitivity-relaxed",
        lambda item: item["policy"].update({"minimum_sensitivity_wilson_lower": 0.5}),
    )
    scenario(
        "false-positive-gate-relaxed",
        lambda item: item["policy"].update(
            {"maximum_false_positive_rate_wilson_upper": 0.1}
        ),
    )
    scenario(
        "lead-time-removed", lambda item: item["policy"].pop("minimum_p10_lead_samples")
    )
    scenario(
        "post-label-tuning",
        lambda item: item.update({"threshold_tuning_after_labels": True}),
    )
    scenario(
        "outcome-injection", lambda item: item.update({"expected_shared_cooling": True})
    )
    scenario(
        "unknown-extension", lambda item: item.update({"preferred_result": "best-run"})
    )
    scenario(
        "authority-escalation", lambda item: item.update({"deployment_authority": True})
    )

    report = {
        "schema_version": 1,
        "experiment_id": "TP-EXP-0037",
        "scenario": "aegis-predeclared-statistical-calibration-contract",
        "simulation": True,
        "hardware_isolated": True,
        "production_mutation": False,
        "control_authority": False,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "predeclared_count": sum(
                item["status"] == STATUS_READY for item in results
            ),
            "hold_count": sum(item["status"] == "HOLD" for item in results),
            "unsafe_ready_count": sum(
                item["status"] == STATUS_READY
                and (
                    item["contract_locked"] is not True
                    or item["deployment_authority"] is not False
                    or item["hardware_authority"] is not False
                )
                for item in results
            ),
            "minimum_positive_cases": base["policy"]["minimum_positive_cases"],
            "minimum_negative_cases": base["policy"]["minimum_negative_cases"],
            "minimum_cohort_cases": base["feasibility"]["minimum_cohort_cases"],
            "perfect_sensitivity_wilson_lower": base["feasibility"][
                "perfect_sensitivity_wilson_lower"
            ],
            "zero_false_positive_rate_wilson_upper": base["feasibility"][
                "zero_false_positive_rate_wilson_upper"
            ],
            "zero_abstention_rate_wilson_upper": base["feasibility"][
                "zero_abstention_rate_wilson_upper"
            ],
            "labels_accepted": 0,
            "scores_accepted": 0,
            "field_validations": 0,
            "candidate_acceptances": 0,
            "candidate_installations": 0,
            "deployments": 0,
            "hardware_actions": 0,
            "runtime_writes": 0,
        },
        "invalidated_assumption": (
            "Metric names are sufficient protection against calibration bias; sample floors, "
            "interval rules, lead-time populations, abstentions, and tuning boundaries must all "
            "be locked before authenticated labels are revealed."
        ),
    }
    report["evidence_sha256"] = _sha256(report)
    return report


__all__ = ["run_temperature_statistical_calibration_contract_checkride"]
