"""Fail-closed, non-executing gate for a manually promoted AEGIS successor."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath
from typing import Any

from .acceptance import semantic_sha256

PROMOTION_REQUEST_SCHEMA = "truepanel.aegis-promotion-request/v1"
PROMOTION_GATE_SCHEMA = "truepanel.aegis-manual-promotion-gate/v1"


def build_promotion_request(
    *,
    request_id: str,
    candidate: Mapping[str, Any],
    stage_manifest: Mapping[str, Any],
    stage_tree_sha256: str,
    backup_root: str,
    nonce: str,
) -> dict[str, Any]:
    """Describe exact staged inputs; this function performs no filesystem work."""

    return {
        "schema": PROMOTION_REQUEST_SCHEMA,
        "request_id": request_id,
        "candidate_envelope_sha256": semantic_sha256(candidate),
        "stage_manifest_sha256": semantic_sha256(stage_manifest),
        "stage_tree_sha256": stage_tree_sha256,
        "stage_root": stage_manifest.get("stage_root"),
        "deploy_root": stage_manifest.get("deploy_root"),
        "backup_root": backup_root,
        "source_version": stage_manifest.get("source_version"),
        "deployed_version": stage_manifest.get("deployed_version"),
        "nonce": nonce,
    }


def evaluate_manual_promotion(
    *,
    request: Mapping[str, Any],
    candidate: Mapping[str, Any],
    stage_manifest: Mapping[str, Any],
    observed_stage_tree_sha256: str,
    acceptance: Mapping[str, Any],
    receipt: Mapping[str, Any],
    preflight: Mapping[str, Any],
    consumed_receipts: Sequence[str] = (),
) -> dict[str, Any]:
    """Decide readiness without writing, restarting, promoting, or consuming."""

    conditions: list[dict[str, Any]] = []

    def add(name: str, passed: bool, reason: str) -> None:
        conditions.append({"condition": name, "passed": bool(passed), "reason": reason})

    request_digest = semantic_sha256(request)
    receipt_digest = semantic_sha256(receipt)
    add(
        "request_schema",
        request.get("schema") == PROMOTION_REQUEST_SCHEMA,
        "RequestSchemaMatched"
        if request.get("schema") == PROMOTION_REQUEST_SCHEMA
        else "RequestSchemaInvalid",
    )
    add(
        "independent_review",
        acceptance.get("status") == "ELIGIBLE_FOR_OPERATOR_PROMOTION",
        "IndependentReviewVerified"
        if acceptance.get("status") == "ELIGIBLE_FOR_OPERATOR_PROMOTION"
        else "IndependentReviewMissing",
    )
    add(
        "signed_request_binding",
        receipt.get("promotion_request_sha256") == request_digest,
        "PromotionRequestBound"
        if receipt.get("promotion_request_sha256") == request_digest
        else "PromotionRequestDigestMismatch",
    )
    add(
        "receipt_not_replayed",
        receipt_digest not in set(consumed_receipts),
        "ReceiptUnused"
        if receipt_digest not in set(consumed_receipts)
        else "ReceiptAlreadyConsumed",
    )
    add(
        "candidate_binding",
        request.get("candidate_envelope_sha256") == semantic_sha256(candidate),
        "CandidateBound"
        if request.get("candidate_envelope_sha256") == semantic_sha256(candidate)
        else "CandidateDigestMismatch",
    )
    add(
        "manifest_binding",
        request.get("stage_manifest_sha256") == semantic_sha256(stage_manifest),
        "ManifestBound"
        if request.get("stage_manifest_sha256") == semantic_sha256(stage_manifest)
        else "ManifestDigestMismatch",
    )
    add(
        "stage_tree_binding",
        request.get("stage_tree_sha256") == observed_stage_tree_sha256
        and len(str(observed_stage_tree_sha256)) == 64,
        "StageTreeBound"
        if request.get("stage_tree_sha256") == observed_stage_tree_sha256
        and len(str(observed_stage_tree_sha256)) == 64
        else "StageTreeDigestMismatch",
    )
    stage_valid = (
        stage_manifest.get("state") == "validated"
        and stage_manifest.get("promotion_performed") is False
        and stage_manifest.get("services_modified") is False
    )
    add(
        "validated_stage",
        stage_valid,
        "StageValidated" if stage_valid else "StageNotPristine",
    )
    add(
        "version_binding",
        request.get("source_version")
        == candidate.get("truepanel_version")
        == stage_manifest.get("source_version"),
        "VersionBound"
        if request.get("source_version")
        == candidate.get("truepanel_version")
        == stage_manifest.get("source_version")
        else "VersionMismatch",
    )

    stage = PurePosixPath(str(request.get("stage_root") or ""))
    deploy = PurePosixPath(str(request.get("deploy_root") or ""))
    backup = PurePosixPath(str(request.get("backup_root") or ""))
    paths_safe = (
        stage.is_absolute()
        and deploy.is_absolute()
        and backup.is_absolute()
        and len({stage, deploy, backup}) == 3
        and backup.parent == deploy.parent
        and backup.name.startswith(".truepanel-backup-")
    )
    add(
        "safe_paths", paths_safe, "PathsBound" if paths_safe else "UnsafePromotionPaths"
    )
    nonce_ok = isinstance(request.get("nonce"), str) and len(request["nonce"]) >= 24
    add("one_time_nonce", nonce_ok, "NoncePresent" if nonce_ok else "NonceInvalid")
    preflight_clear = (
        preflight.get("status") == "CLEAR"
        and preflight.get("active_incident") is False
        and preflight.get("services_healthy") is True
        and preflight.get("pools_online") is True
        and preflight.get("safety_hold") is False
        and preflight.get("rollback_verified") is True
    )
    add(
        "promotion_preflight",
        preflight_clear,
        "PreflightClear" if preflight_clear else "PreflightHold",
    )

    failed = [item for item in conditions if not item["passed"]]
    return {
        "schema": PROMOTION_GATE_SCHEMA,
        "status": "READY_FOR_MANUAL_PROMOTION" if not failed else "HOLD",
        "reason": "ManualPromotionChecksPassed" if not failed else failed[0]["reason"],
        "conditions": conditions,
        "request_sha256": request_digest,
        "receipt_sha256": receipt_digest,
        "requires_confirmation": "PROMOTE_TRUEPANEL",
        "receipt_consumed": False,
        "promotion_performed": False,
        "services_modified": False,
        "runtime_writes": 0,
        "production_mutation": False,
        "control_authority": False,
    }


__all__ = [
    "PROMOTION_GATE_SCHEMA",
    "PROMOTION_REQUEST_SCHEMA",
    "build_promotion_request",
    "evaluate_manual_promotion",
]
