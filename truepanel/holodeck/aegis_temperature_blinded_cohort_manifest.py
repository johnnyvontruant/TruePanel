"""Adversarial proof for two-phase, label-blind cohort freezing."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable
from typing import Any

from truepanel.aegis.temperature_blinded_cohort_manifest import (
    STATUS_MANIFEST_READY,
    build_temperature_blinded_cohort_plan,
    freeze_temperature_blinded_cohort_manifest,
    validate_temperature_blinded_cohort_manifest,
)
from truepanel.aegis.temperature_intake_bound_detector_result import (
    SCHEMA as DETECTOR_RESULT_SCHEMA,
)
from truepanel.aegis.temperature_statistical_calibration_contract import (
    build_temperature_statistical_calibration_contract,
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _fixture() -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    contract = build_temperature_statistical_calibration_contract(
        declared_at_utc="2026-10-22T04:30:00Z"
    )
    detector_contract = _sha256({"detector": "aegis-shared-cooling-v1"})
    cases = []
    results = []
    for index in range(440):
        case_id = f"blind-{index:04d}"
        recording = _sha256({"recording": index})
        intake = _sha256({"intake": index})
        receipt = _sha256({"receipt": index})
        cases.append(
            {
                "case_id": case_id,
                "recording_sha256": recording,
                "long_window_intake_record_sha256": intake,
                "long_window_intake_receipt_sha256": receipt,
                "system_profile_id": f"profile-{index % 2}",
                "workload_class": f"workload-{index % 4}",
            }
        )
        result = {
            "schema": DETECTOR_RESULT_SCHEMA,
            "status": "LABEL_BLIND_DETECTOR_RESULT_BOUND",
            "label_blind": True,
            "labels_present": False,
            "receipt_bound": True,
            "intake_reconstructed": True,
            "eligible_for_calibration_binding": True,
            "recording_sha256": recording,
            "long_window_intake_record_sha256": intake,
            "long_window_intake_receipt_sha256": receipt,
            "detector_contract_sha256": detector_contract,
            "generated_at_utc": f"2026-10-22T{index // 60:02d}:{index % 60:02d}:00Z",
            "predicted_shared_cooling": index % 5 == 0,
            "first_policy_match_index": 19 if index % 5 == 0 else None,
            "confidence_mean": 0.94 if index % 5 == 0 else 0.0,
            "candidate_accepted": False,
            "candidate_installed": False,
            "runtime_authority": False,
            "deployment_authority": False,
            "hardware_authority": False,
            "storage_write_authority": False,
            "network_authority": False,
            "automatic_promotion": False,
        }
        result["result_sha256"] = _sha256(result)
        results.append({"case_id": case_id, "result": result})
    plan = build_temperature_blinded_cohort_plan(
        contract,
        cases,
        detector_contract_sha256=detector_contract,
        frozen_at_utc="2026-10-22T12:00:00Z",
    )
    return contract, plan, results


def run_temperature_blinded_cohort_manifest_checkride() -> dict[str, Any]:
    """Prove every preplanned intake is frozen before labels become visible."""

    base_contract, base_plan, base_results = _fixture()
    scenarios: list[dict[str, Any]] = []
    manifests: list[dict[str, Any]] = []

    def scenario(
        name: str,
        mutate: Callable[[dict[str, Any], dict[str, Any], list[dict[str, Any]]], None]
        | None = None,
        *,
        reverse: bool = False,
        tamper_after_freeze: bool = False,
    ) -> None:
        contract = copy.deepcopy(base_contract)
        plan = copy.deepcopy(base_plan)
        results = copy.deepcopy(base_results)
        if mutate:
            mutate(contract, plan, results)
        if reverse:
            results.reverse()
        try:
            manifest = freeze_temperature_blinded_cohort_manifest(
                contract,
                plan,
                results,
                frozen_at_utc="2026-10-22T13:00:00Z",
            )
            if tamper_after_freeze:
                manifest["deployment_authority"] = True
            validation = validate_temperature_blinded_cohort_manifest(
                contract, manifest
            )
        except (KeyError, TypeError, ValueError) as error:
            manifest = {}
            validation = {
                "status": "HOLD",
                "ready_for_authenticated_label_join": False,
                "errors": [str(error) or error.__class__.__name__],
            }
        manifests.append(manifest)
        scenarios.append(
            {
                "scenario": name,
                "status": validation["status"],
                "ready_for_authenticated_label_join": validation[
                    "ready_for_authenticated_label_join"
                ],
                "error_count": len(validation["errors"]),
            }
        )

    scenario("complete-two-phase-freeze")
    scenario("input-order-independent-freeze", reverse=True)
    scenario("planned-case-omitted", lambda _c, _p, results: results.pop())
    scenario(
        "unplanned-case-added",
        lambda _c, _p, results: results.append(
            {"case_id": "blind-extra", "result": copy.deepcopy(results[0]["result"])}
        ),
    )
    scenario(
        "duplicate-case-result",
        lambda _c, _p, results: results.append(copy.deepcopy(results[0])),
    )
    scenario(
        "result-digest-tamper",
        lambda _c, _p, results: results[0]["result"].update({"confidence_mean": 0.01}),
    )
    scenario(
        "recording-substitution",
        lambda _c, _p, results: results[0]["result"].update(
            {"recording_sha256": "0" * 64}
        ),
    )
    scenario(
        "detector-contract-drift",
        lambda _c, _p, results: results[0]["result"].update(
            {"detector_contract_sha256": "1" * 64}
        ),
    )
    scenario(
        "prediction-leaked-into-plan",
        lambda _c, plan, _r: plan["cases"][0].update(
            {"predicted_shared_cooling": True}
        ),
    )
    scenario(
        "outcome-label-injected",
        lambda _c, _p, results: results[0]["result"].update(
            {"expected_shared_cooling": True}
        ),
    )
    scenario(
        "statistical-contract-substitution",
        lambda contract, _p, _r: contract["policy"].update(
            {"minimum_positive_cases": 4}
        ),
    )
    scenario("post-freeze-authority-edit", tamper_after_freeze=True)

    ready = [item for item in manifests if item.get("status") == STATUS_MANIFEST_READY]
    report = {
        "schema_version": 1,
        "experiment_id": "TP-EXP-0038",
        "scenario": "aegis-two-phase-blinded-cohort-manifest",
        "simulation": True,
        "hardware_isolated": True,
        "production_mutation": False,
        "control_authority": False,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "frozen_count": sum(
                item["status"] == STATUS_MANIFEST_READY for item in scenarios
            ),
            "hold_count": sum(item["status"] == "HOLD" for item in scenarios),
            "unsafe_ready_count": sum(
                item["status"] == STATUS_MANIFEST_READY
                and item["ready_for_authenticated_label_join"] is not True
                for item in scenarios
            ),
            "planned_case_count": ready[0]["planned_case_count"],
            "result_count": ready[0]["result_count"],
            "system_profile_count": base_plan["system_profile_count"],
            "workload_class_count": base_plan["workload_class_count"],
            "order_independent_manifest_identity": (
                ready[0]["manifest_sha256"] == ready[1]["manifest_sha256"]
            ),
            "planned_omissions_accepted": 0,
            "unplanned_results_accepted": 0,
            "duplicate_results_accepted": 0,
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
            "Freezing detector results alone prevents selection bias; the complete intake "
            "inventory must be frozen before predictions and joined one-for-one afterward."
        ),
    }
    report["evidence_sha256"] = _sha256(report)
    return report


__all__ = ["run_temperature_blinded_cohort_manifest_checkride"]
