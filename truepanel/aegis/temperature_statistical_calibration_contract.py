"""Predeclared statistical gates for label-blind temperature calibration."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Final

from .evidence_gate import wilson_interval
from .temperature_intake_bound_detector_result import SCHEMA as DETECTOR_RESULT_SCHEMA

SCHEMA: Final = "truepanel.aegis-temperature-statistical-calibration-contract/v1"
STATUS_READY: Final = "STATISTICAL_CALIBRATION_CONTRACT_PREDECLARED"
STATUS_HOLD: Final = "HOLD"
POLICY_ID: Final = "aegis-shared-cooling-field-calibration-v1"
CONFIDENCE_Z: Final = 1.959963984540054


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("StatisticalCalibrationContractTimeInvalid")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo != UTC:
        raise ValueError("StatisticalCalibrationContractTimeInvalid")
    return parsed


def _policy() -> dict[str, Any]:
    return {
        "confidence_level": 0.95,
        "confidence_interval": "wilson-score-two-sided",
        "minimum_positive_cases": 40,
        "minimum_negative_cases": 400,
        "minimum_system_profiles": 2,
        "minimum_workload_classes": 4,
        "minimum_threshold_landmark_positive_cases": 20,
        "minimum_sensitivity_wilson_lower": 0.80,
        "maximum_false_positive_rate_wilson_upper": 0.01,
        "maximum_abstention_rate_wilson_upper": 0.01,
        "minimum_median_lead_samples": 12,
        "minimum_p10_lead_samples": 4,
    }


def _feasibility(policy: Mapping[str, Any]) -> dict[str, Any]:
    positives = int(policy["minimum_positive_cases"])
    negatives = int(policy["minimum_negative_cases"])
    total = positives + negatives
    sensitivity_lower = wilson_interval(positives, positives, z=CONFIDENCE_Z)[0]
    false_positive_upper = wilson_interval(0, negatives, z=CONFIDENCE_Z)[1]
    abstention_upper = wilson_interval(0, total, z=CONFIDENCE_Z)[1]
    feasible = (
        sensitivity_lower >= float(policy["minimum_sensitivity_wilson_lower"])
        and false_positive_upper
        <= float(policy["maximum_false_positive_rate_wilson_upper"])
        and abstention_upper <= float(policy["maximum_abstention_rate_wilson_upper"])
    )
    return {
        "minimum_cohort_cases": total,
        "perfect_sensitivity_wilson_lower": round(sensitivity_lower, 6),
        "zero_false_positive_rate_wilson_upper": round(false_positive_upper, 6),
        "zero_abstention_rate_wilson_upper": round(abstention_upper, 6),
        "policy_mathematically_feasible": feasible,
    }


def build_temperature_statistical_calibration_contract(
    *, declared_at_utc: str
) -> dict[str, Any]:
    """Build the fixed policy without accepting a recording, result, or label."""

    _utc(declared_at_utc)
    policy = _policy()
    result = {
        "schema": SCHEMA,
        "status": STATUS_READY,
        "policy_id": POLICY_ID,
        "declared_at_utc": declared_at_utc,
        "detector_result_schema": DETECTOR_RESULT_SCHEMA,
        "locked_before_labels": True,
        "threshold_tuning_after_labels": False,
        "case_exclusion_after_scoring": False,
        "single_evaluation_per_detector_contract": True,
        "immutable_cohort_manifest_required": True,
        "every_case_accounted_for": True,
        "abstention_is_not_a_negative": True,
        "lead_time_population": "true-positive-cases-with-isolated-threshold-landmark",
        "policy": policy,
        "feasibility": _feasibility(policy),
        "labels_present": False,
        "cohort_present": False,
        "scores_present": False,
        "field_validated": False,
        "production_validated": False,
        "candidate_accepted": False,
        "candidate_installed": False,
        "runtime_authority": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "storage_write_authority": False,
        "network_authority": False,
        "automatic_promotion": False,
    }
    result["contract_sha256"] = _sha256(result)
    return result


def _contains_outcomes(value: Any) -> bool:
    forbidden = {
        "expected_shared_cooling",
        "outcome",
        "label",
        "labels",
        "true_positive",
        "true_negative",
        "false_positive",
        "false_negative",
        "observed_sensitivity",
        "observed_specificity",
    }
    if isinstance(value, Mapping):
        return any(
            str(key).strip().lower() in forbidden or _contains_outcomes(nested)
            for key, nested in value.items()
        )
    if isinstance(value, list):
        return any(_contains_outcomes(item) for item in value)
    return False


def validate_temperature_statistical_calibration_contract(
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Reconstruct the exact policy and reject any post-label policy freedom."""

    errors: list[str] = []
    if _contains_outcomes(contract):
        errors.append("statistical contract must not contain outcomes or labels")
    declared_at = contract.get("declared_at_utc")
    try:
        expected = build_temperature_statistical_calibration_contract(
            declared_at_utc=str(declared_at)
        )
    except (TypeError, ValueError):
        expected = None
        errors.append("statistical contract declaration time is invalid")
    if expected is not None and dict(contract) != expected:
        errors.append("statistical contract differs from the fixed predeclared policy")
    feasibility = contract.get("feasibility")
    if (
        not isinstance(feasibility, Mapping)
        or feasibility.get("policy_mathematically_feasible") is not True
    ):
        errors.append("statistical policy is not mathematically feasible")
    policy = contract.get("policy")
    if isinstance(policy, Mapping):
        for value in policy.values():
            if isinstance(value, float) and not math.isfinite(value):
                errors.append("statistical policy contains a non-finite value")
                break
    else:
        errors.append("statistical policy is missing")
    errors = list(dict.fromkeys(errors))
    ready = not errors
    return {
        "schema": SCHEMA,
        "status": STATUS_READY if ready else STATUS_HOLD,
        "contract_sha256": contract.get("contract_sha256") if ready else None,
        "contract_locked": ready,
        "ready_for_blinded_cohort_collection": ready,
        "eligible_for_independent_scoring": False,
        "labels_accepted": False,
        "scores_accepted": False,
        "field_validated": False,
        "production_validated": False,
        "candidate_accepted": False,
        "candidate_installed": False,
        "runtime_authority": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "storage_write_authority": False,
        "network_authority": False,
        "automatic_promotion": False,
        "errors": errors,
    }


def pending_temperature_statistical_calibration_contract() -> dict[str, Any]:
    """Expose the locked policy while honestly reporting that no cohort exists."""

    contract = build_temperature_statistical_calibration_contract(
        declared_at_utc="2026-10-22T04:30:00Z"
    )
    return {
        **contract,
        "cohort_present": False,
        "scores_present": False,
        "ready_for_blinded_cohort_collection": True,
        "eligible_for_independent_scoring": False,
        "next_action": (
            "freeze an immutable label-blind cohort manifest, create every detector "
            "result, then reveal authenticated outcomes for one independent score"
        ),
    }


__all__ = [
    "POLICY_ID",
    "SCHEMA",
    "STATUS_HOLD",
    "STATUS_READY",
    "build_temperature_statistical_calibration_contract",
    "pending_temperature_statistical_calibration_contract",
    "validate_temperature_statistical_calibration_contract",
]
