"""Two-phase, label-blind cohort freezing for temperature calibration."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Final

from .temperature_intake_bound_detector_result import SCHEMA as DETECTOR_RESULT_SCHEMA
from .temperature_statistical_calibration_contract import (
    STATUS_READY as CONTRACT_READY,
)
from .temperature_statistical_calibration_contract import (
    validate_temperature_statistical_calibration_contract,
)

PLAN_SCHEMA: Final = "truepanel.aegis-temperature-blinded-cohort-plan/v1"
MANIFEST_SCHEMA: Final = "truepanel.aegis-temperature-blinded-cohort-manifest/v1"
STATUS_PLAN_READY: Final = "BLINDED_COHORT_PLAN_FROZEN"
STATUS_MANIFEST_READY: Final = "BLINDED_COHORT_MANIFEST_FROZEN"
STATUS_HOLD: Final = "HOLD"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_OPAQUE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
_PLAN_CASE_KEYS = {
    "case_id",
    "recording_sha256",
    "long_window_intake_record_sha256",
    "long_window_intake_receipt_sha256",
    "system_profile_id",
    "workload_class",
}
_RESULT_DESCRIPTOR_KEYS = {
    "case_id",
    "recording_sha256",
    "long_window_intake_record_sha256",
    "long_window_intake_receipt_sha256",
    "result_sha256",
    "generated_at_utc",
    "predicted_shared_cooling",
    "first_policy_match_index",
    "confidence_mean",
}
_OUTCOME_KEYS = {
    "expected_shared_cooling",
    "outcome",
    "label",
    "labels",
    "ground_truth",
    "true_positive",
    "true_negative",
    "false_positive",
    "false_negative",
}
_PREDICTION_KEYS = {
    "prediction",
    "predicted_shared_cooling",
    "first_policy_match_index",
    "confidence_mean",
    "result_sha256",
}


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("BlindedCohortTimeInvalid")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo != UTC:
        raise ValueError("BlindedCohortTimeInvalid")
    return parsed


def _has_key(value: Any, forbidden: set[str]) -> bool:
    if isinstance(value, Mapping):
        return any(
            str(key).strip().lower() in forbidden or _has_key(nested, forbidden)
            for key, nested in value.items()
        )
    if isinstance(value, list):
        return any(_has_key(item, forbidden) for item in value)
    return False


def _valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _contract_sha256(contract: Mapping[str, Any]) -> str:
    validation = validate_temperature_statistical_calibration_contract(contract)
    if validation["status"] != CONTRACT_READY:
        raise ValueError("StatisticalCalibrationContractNotReady")
    digest = validation.get("contract_sha256")
    if not _valid_sha256(digest):
        raise ValueError("StatisticalCalibrationContractDigestInvalid")
    return str(digest)


def _validate_plan_case(case: Mapping[str, Any]) -> None:
    if set(case) != _PLAN_CASE_KEYS:
        raise ValueError("BlindedCohortPlanCaseFieldsInvalid")
    if not isinstance(case["case_id"], str) or not _OPAQUE_ID.fullmatch(
        case["case_id"]
    ):
        raise ValueError("BlindedCohortPlanCaseIdentityInvalid")
    for key in (
        "recording_sha256",
        "long_window_intake_record_sha256",
        "long_window_intake_receipt_sha256",
    ):
        if not _valid_sha256(case[key]):
            raise ValueError("BlindedCohortPlanDigestInvalid")
    for key in ("system_profile_id", "workload_class"):
        if not isinstance(case[key], str) or not _OPAQUE_ID.fullmatch(case[key]):
            raise ValueError("BlindedCohortPlanStratumInvalid")
    if _has_key(case, _OUTCOME_KEYS | _PREDICTION_KEYS):
        raise ValueError("BlindedCohortPlanMustPrecedePredictionsAndLabels")


def build_temperature_blinded_cohort_plan(
    contract: Mapping[str, Any],
    cases: Sequence[Mapping[str, Any]],
    *,
    detector_contract_sha256: str,
    frozen_at_utc: str,
) -> dict[str, Any]:
    """Freeze the complete intake inventory before predictions or labels exist."""

    contract_digest = _contract_sha256(contract)
    _utc(frozen_at_utc)
    if not _valid_sha256(detector_contract_sha256):
        raise ValueError("BlindedCohortDetectorContractDigestInvalid")
    normalized = [dict(case) for case in cases]
    for case in normalized:
        _validate_plan_case(case)
    normalized.sort(key=lambda item: item["case_id"])
    minimum = int(contract["feasibility"]["minimum_cohort_cases"])
    if len(normalized) < minimum:
        raise ValueError("BlindedCohortPlanBelowMinimumCaseFloor")
    for key in (
        "case_id",
        "recording_sha256",
        "long_window_intake_record_sha256",
        "long_window_intake_receipt_sha256",
    ):
        values = [case[key] for case in normalized]
        if len(values) != len(set(values)):
            raise ValueError("BlindedCohortPlanDuplicateMember")
    profile_count = len({case["system_profile_id"] for case in normalized})
    workload_count = len({case["workload_class"] for case in normalized})
    if profile_count < int(contract["policy"]["minimum_system_profiles"]):
        raise ValueError("BlindedCohortPlanProfileFloorNotMet")
    if workload_count < int(contract["policy"]["minimum_workload_classes"]):
        raise ValueError("BlindedCohortPlanWorkloadFloorNotMet")
    plan = {
        "schema": PLAN_SCHEMA,
        "status": STATUS_PLAN_READY,
        "frozen_at_utc": frozen_at_utc,
        "statistical_contract_sha256": contract_digest,
        "detector_result_schema": DETECTOR_RESULT_SCHEMA,
        "detector_contract_sha256": detector_contract_sha256,
        "case_count": len(normalized),
        "system_profile_count": profile_count,
        "workload_class_count": workload_count,
        "inventory_complete": True,
        "predictions_present": False,
        "labels_present": False,
        "cases": normalized,
    }
    plan["plan_sha256"] = _sha256(plan)
    return plan


def validate_temperature_blinded_cohort_plan(
    contract: Mapping[str, Any], plan: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate plan structure, digest, strata, and pre-prediction boundary."""

    errors: list[str] = []
    try:
        contract_digest = _contract_sha256(contract)
    except (TypeError, ValueError) as error:
        contract_digest = None
        errors.append(str(error))
    expected_keys = {
        "schema",
        "status",
        "frozen_at_utc",
        "statistical_contract_sha256",
        "detector_result_schema",
        "detector_contract_sha256",
        "case_count",
        "system_profile_count",
        "workload_class_count",
        "inventory_complete",
        "predictions_present",
        "labels_present",
        "cases",
        "plan_sha256",
    }
    if set(plan) != expected_keys:
        errors.append("blinded cohort plan fields differ from the fixed schema")
    try:
        _utc(plan.get("frozen_at_utc"))
    except (TypeError, ValueError):
        errors.append("blinded cohort plan time is invalid")
    cases = plan.get("cases")
    if not isinstance(cases, list):
        errors.append("blinded cohort plan cases are missing")
        cases = []
    try:
        for case in cases:
            if not isinstance(case, Mapping):
                raise ValueError("BlindedCohortPlanCaseInvalid")
            _validate_plan_case(case)
    except (TypeError, ValueError) as error:
        errors.append(str(error))
    body = dict(plan)
    supplied_digest = body.pop("plan_sha256", None)
    if not _valid_sha256(supplied_digest) or _sha256(body) != supplied_digest:
        errors.append("blinded cohort plan digest does not match its content")
    if (
        contract_digest is not None
        and plan.get("statistical_contract_sha256") != contract_digest
    ):
        errors.append("blinded cohort plan is bound to another statistical contract")
    if plan.get("schema") != PLAN_SCHEMA or plan.get("status") != STATUS_PLAN_READY:
        errors.append("blinded cohort plan schema or status is invalid")
    if plan.get("detector_result_schema") != DETECTOR_RESULT_SCHEMA:
        errors.append("blinded cohort plan names another detector-result schema")
    if not _valid_sha256(plan.get("detector_contract_sha256")):
        errors.append("blinded cohort detector contract digest is invalid")
    minimum = int(contract.get("feasibility", {}).get("minimum_cohort_cases", 0))
    if len(cases) < minimum or plan.get("case_count") != len(cases):
        errors.append("blinded cohort plan case floor or count is invalid")
    valid_cases = [case for case in cases if isinstance(case, Mapping)]
    for key in (
        "case_id",
        "recording_sha256",
        "long_window_intake_record_sha256",
        "long_window_intake_receipt_sha256",
    ):
        values = [case.get(key) for case in valid_cases]
        if len(values) != len(cases) or len(values) != len(set(values)):
            errors.append("blinded cohort plan contains duplicate member identity")
            break
    case_ids = [case.get("case_id") for case in valid_cases]
    if (
        len(case_ids) != len(cases)
        or any(not isinstance(case_id, str) for case_id in case_ids)
        or case_ids != sorted(case_ids)
    ):
        errors.append("blinded cohort plan cases are not in canonical order")
    profile_count = len({case.get("system_profile_id") for case in valid_cases})
    workload_count = len({case.get("workload_class") for case in valid_cases})
    if plan.get("system_profile_count") != profile_count or profile_count < int(
        contract.get("policy", {}).get("minimum_system_profiles", 0)
    ):
        errors.append("blinded cohort plan profile floor or count is invalid")
    if plan.get("workload_class_count") != workload_count or workload_count < int(
        contract.get("policy", {}).get("minimum_workload_classes", 0)
    ):
        errors.append("blinded cohort plan workload floor or count is invalid")
    if _has_key(plan, _OUTCOME_KEYS) or plan.get("labels_present") is not False:
        errors.append("blinded cohort plan contains outcome labels")
    if (
        plan.get("predictions_present") is not False
        or plan.get("inventory_complete") is not True
    ):
        errors.append("blinded cohort inventory was not frozen before predictions")
    errors = list(dict.fromkeys(errors))
    ready = not errors
    return {
        "schema": PLAN_SCHEMA,
        "status": STATUS_PLAN_READY if ready else STATUS_HOLD,
        "plan_sha256": supplied_digest if ready else None,
        "case_count": len(cases) if ready else 0,
        "inventory_complete": ready,
        "ready_for_label_blind_detector_join": ready,
        "labels_accepted": False,
        "errors": errors,
    }


def _validate_detector_result(
    result: Mapping[str, Any], plan: Mapping[str, Any]
) -> None:
    if _has_key(result, _OUTCOME_KEYS):
        raise ValueError("BlindedCohortDetectorResultContainsLabels")
    if (
        result.get("schema") != DETECTOR_RESULT_SCHEMA
        or result.get("status") != "LABEL_BLIND_DETECTOR_RESULT_BOUND"
        or result.get("label_blind") is not True
        or result.get("labels_present") is not False
        or result.get("receipt_bound") is not True
        or result.get("intake_reconstructed") is not True
        or result.get("eligible_for_calibration_binding") is not True
    ):
        raise ValueError("BlindedCohortDetectorResultNotReady")
    if result.get("detector_contract_sha256") != plan["detector_contract_sha256"]:
        raise ValueError("BlindedCohortDetectorContractDrift")
    for key in (
        "candidate_accepted",
        "candidate_installed",
        "runtime_authority",
        "deployment_authority",
        "hardware_authority",
        "storage_write_authority",
        "network_authority",
        "automatic_promotion",
    ):
        if result.get(key) is not False:
            raise ValueError("BlindedCohortDetectorResultAuthorityInvalid")
    supplied = result.get("result_sha256")
    body = dict(result)
    body.pop("result_sha256", None)
    if not _valid_sha256(supplied) or _sha256(body) != supplied:
        raise ValueError("BlindedCohortDetectorResultDigestMismatch")
    _utc(result.get("generated_at_utc"))


def freeze_temperature_blinded_cohort_manifest(
    contract: Mapping[str, Any],
    plan: Mapping[str, Any],
    results: Sequence[Mapping[str, Any]],
    *,
    frozen_at_utc: str,
) -> dict[str, Any]:
    """Join every planned intake to exactly one label-blind detector result."""

    contract_digest = _contract_sha256(contract)
    plan_validation = validate_temperature_blinded_cohort_plan(contract, plan)
    if plan_validation["status"] != STATUS_PLAN_READY:
        raise ValueError("BlindedCohortPlanNotReady")
    _utc(frozen_at_utc)
    planned = {case["case_id"]: case for case in plan["cases"]}
    joined: dict[str, Mapping[str, Any]] = {}
    for envelope in results:
        if set(envelope) != {"case_id", "result"}:
            raise ValueError("BlindedCohortResultEnvelopeInvalid")
        case_id = envelope["case_id"]
        result = envelope["result"]
        if case_id in joined:
            raise ValueError("BlindedCohortDuplicateResult")
        if case_id not in planned:
            raise ValueError("BlindedCohortUnplannedResult")
        if not isinstance(result, Mapping):
            raise ValueError("BlindedCohortDetectorResultInvalid")
        _validate_detector_result(result, plan)
        case = planned[case_id]
        for key in (
            "recording_sha256",
            "long_window_intake_record_sha256",
            "long_window_intake_receipt_sha256",
        ):
            if result.get(key) != case[key]:
                raise ValueError("BlindedCohortResultDoesNotMatchPlan")
        joined[case_id] = result
    if set(joined) != set(planned):
        raise ValueError("BlindedCohortPlannedResultMissing")
    result_digests = [result["result_sha256"] for result in joined.values()]
    if len(result_digests) != len(set(result_digests)):
        raise ValueError("BlindedCohortDuplicateResultDigest")
    descriptors = []
    for case_id in sorted(joined):
        result = joined[case_id]
        descriptors.append(
            {
                key: case_id if key == "case_id" else result[key]
                for key in _RESULT_DESCRIPTOR_KEYS
            }
        )
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "status": STATUS_MANIFEST_READY,
        "frozen_at_utc": frozen_at_utc,
        "statistical_contract_sha256": contract_digest,
        "plan_sha256": plan["plan_sha256"],
        "detector_result_schema": DETECTOR_RESULT_SCHEMA,
        "detector_contract_sha256": plan["detector_contract_sha256"],
        "planned_case_count": plan["case_count"],
        "result_count": len(descriptors),
        "all_planned_cases_accounted_for": True,
        "post_freeze_mutation_allowed": False,
        "labels_present": False,
        "scores_present": False,
        "results": descriptors,
        "ready_for_authenticated_label_join": True,
        "eligible_for_independent_scoring": False,
        "field_validated": False,
        "candidate_accepted": False,
        "candidate_installed": False,
        "runtime_authority": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "storage_write_authority": False,
        "network_authority": False,
        "automatic_promotion": False,
    }
    manifest["manifest_sha256"] = _sha256(manifest)
    return manifest


def validate_temperature_blinded_cohort_manifest(
    contract: Mapping[str, Any], manifest: Mapping[str, Any]
) -> dict[str, Any]:
    """Fail closed if a frozen manifest or any authority field changes."""

    errors: list[str] = []
    try:
        contract_digest = _contract_sha256(contract)
    except (TypeError, ValueError) as error:
        contract_digest = None
        errors.append(str(error))
    expected_keys = {
        "schema",
        "status",
        "frozen_at_utc",
        "statistical_contract_sha256",
        "plan_sha256",
        "detector_result_schema",
        "detector_contract_sha256",
        "planned_case_count",
        "result_count",
        "all_planned_cases_accounted_for",
        "post_freeze_mutation_allowed",
        "labels_present",
        "scores_present",
        "results",
        "ready_for_authenticated_label_join",
        "eligible_for_independent_scoring",
        "field_validated",
        "candidate_accepted",
        "candidate_installed",
        "runtime_authority",
        "deployment_authority",
        "hardware_authority",
        "storage_write_authority",
        "network_authority",
        "automatic_promotion",
        "manifest_sha256",
    }
    if set(manifest) != expected_keys:
        errors.append("blinded cohort manifest fields differ from the fixed schema")
    try:
        _utc(manifest.get("frozen_at_utc"))
    except (TypeError, ValueError):
        errors.append("blinded cohort manifest time is invalid")
    body = dict(manifest)
    supplied = body.pop("manifest_sha256", None)
    if not _valid_sha256(supplied) or _sha256(body) != supplied:
        errors.append("blinded cohort manifest digest does not match its content")
    results = manifest.get("results")
    if not isinstance(results, list):
        results = []
        errors.append("blinded cohort manifest results are missing")
    if any(
        not isinstance(item, Mapping) or set(item) != _RESULT_DESCRIPTOR_KEYS
        for item in results
    ):
        errors.append("blinded cohort manifest result descriptor is invalid")
    valid_results = [item for item in results if isinstance(item, Mapping)]
    for key in (
        "case_id",
        "recording_sha256",
        "long_window_intake_record_sha256",
        "long_window_intake_receipt_sha256",
        "result_sha256",
    ):
        values = [item.get(key) for item in valid_results]
        if len(values) != len(results) or len(values) != len(set(values)):
            errors.append("blinded cohort manifest contains duplicate member identity")
            break
    case_ids = [item.get("case_id") for item in valid_results]
    if (
        len(case_ids) != len(results)
        or any(not isinstance(case_id, str) for case_id in case_ids)
        or case_ids != sorted(case_ids)
    ):
        errors.append("blinded cohort manifest results are not in canonical order")
    for item in valid_results:
        if (
            not isinstance(item.get("case_id"), str)
            or _OPAQUE_ID.fullmatch(item["case_id"]) is None
            or any(
                not _valid_sha256(item.get(key))
                for key in (
                    "recording_sha256",
                    "long_window_intake_record_sha256",
                    "long_window_intake_receipt_sha256",
                    "result_sha256",
                )
            )
            or not isinstance(item.get("predicted_shared_cooling"), bool)
            or (
                item.get("first_policy_match_index") is not None
                and (
                    not isinstance(item["first_policy_match_index"], int)
                    or isinstance(item["first_policy_match_index"], bool)
                    or item["first_policy_match_index"] < 0
                )
            )
            or not isinstance(item.get("confidence_mean"), (int, float))
            or isinstance(item.get("confidence_mean"), bool)
            or not 0 <= float(item["confidence_mean"]) <= 1
        ):
            errors.append("blinded cohort manifest result value is invalid")
            break
        try:
            _utc(item.get("generated_at_utc"))
        except (TypeError, ValueError):
            errors.append("blinded cohort manifest result time is invalid")
            break
    if manifest.get("planned_case_count") != len(results) or manifest.get(
        "result_count"
    ) != len(results):
        errors.append("blinded cohort manifest does not account for every planned case")
    minimum = int(contract.get("feasibility", {}).get("minimum_cohort_cases", 0))
    if len(results) < minimum:
        errors.append("blinded cohort manifest is below the predeclared case floor")
    if (
        contract_digest is not None
        and manifest.get("statistical_contract_sha256") != contract_digest
    ):
        errors.append(
            "blinded cohort manifest is bound to another statistical contract"
        )
    if (
        manifest.get("schema") != MANIFEST_SCHEMA
        or manifest.get("status") != STATUS_MANIFEST_READY
    ):
        errors.append("blinded cohort manifest schema or status is invalid")
    if (
        manifest.get("detector_result_schema") != DETECTOR_RESULT_SCHEMA
        or not _valid_sha256(manifest.get("detector_contract_sha256"))
        or not _valid_sha256(manifest.get("plan_sha256"))
    ):
        errors.append("blinded cohort manifest lineage binding is invalid")
    required_false = (
        "post_freeze_mutation_allowed",
        "labels_present",
        "scores_present",
        "eligible_for_independent_scoring",
        "field_validated",
        "candidate_accepted",
        "candidate_installed",
        "runtime_authority",
        "deployment_authority",
        "hardware_authority",
        "storage_write_authority",
        "network_authority",
        "automatic_promotion",
    )
    if any(manifest.get(key) is not False for key in required_false):
        errors.append("blinded cohort manifest grants forbidden state or authority")
    if (
        manifest.get("all_planned_cases_accounted_for") is not True
        or manifest.get("ready_for_authenticated_label_join") is not True
    ):
        errors.append("blinded cohort manifest is incomplete")
    if _has_key(manifest, _OUTCOME_KEYS):
        errors.append("blinded cohort manifest contains outcome labels")
    errors = list(dict.fromkeys(errors))
    ready = not errors
    return {
        "schema": MANIFEST_SCHEMA,
        "status": STATUS_MANIFEST_READY if ready else STATUS_HOLD,
        "manifest_sha256": supplied if ready else None,
        "case_count": len(results) if ready else 0,
        "ready_for_authenticated_label_join": ready,
        "eligible_for_independent_scoring": False,
        "labels_accepted": False,
        "scores_accepted": False,
        "field_validated": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "errors": errors,
    }


def pending_temperature_blinded_cohort_manifest(
    statistical_contract: Mapping[str, Any],
) -> dict[str, Any]:
    contract_ready = statistical_contract.get("status") == CONTRACT_READY
    return {
        "schema": MANIFEST_SCHEMA,
        "status": "ACTION_REQUIRED_BLINDED_COHORT_PLAN"
        if contract_ready
        else STATUS_HOLD,
        "statistical_contract_ready": contract_ready,
        "plan_present": False,
        "manifest_present": False,
        "planned_case_count": 0,
        "result_count": 0,
        "labels_present": False,
        "scores_present": False,
        "ready_for_authenticated_label_join": False,
        "eligible_for_independent_scoring": False,
        "field_validated": False,
        "candidate_accepted": False,
        "candidate_installed": False,
        "runtime_authority": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "storage_write_authority": False,
        "network_authority": False,
        "automatic_promotion": False,
        "next_action": (
            "freeze the complete label-blind intake inventory before creating detector results"
            if contract_ready
            else "predeclare and validate the statistical calibration contract"
        ),
        "errors": []
        if contract_ready
        else ["predeclared statistical contract required"],
    }


__all__ = [
    "MANIFEST_SCHEMA",
    "PLAN_SCHEMA",
    "STATUS_HOLD",
    "STATUS_MANIFEST_READY",
    "STATUS_PLAN_READY",
    "build_temperature_blinded_cohort_plan",
    "freeze_temperature_blinded_cohort_manifest",
    "pending_temperature_blinded_cohort_manifest",
    "validate_temperature_blinded_cohort_manifest",
    "validate_temperature_blinded_cohort_plan",
]
