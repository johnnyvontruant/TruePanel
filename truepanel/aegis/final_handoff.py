"""Short-lived, non-executing seal for the final human promotion handoff."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from truepanel.upgrade.promotion import PROMOTION_CONFIRMATION

from .acceptance import semantic_sha256
from .stage_witness import witness_validated_stage

HANDOFF_SEAL_SCHEMA = "truepanel.aegis-promotion-handoff-seal/v1"
HANDOFF_DECISION_SCHEMA = "truepanel.aegis-promotion-handoff-decision/v1"
MAX_HANDOFF_LIFETIME_SECONDS = 300

_SEAL_FIELDS = {
    "schema",
    "seal_id",
    "request_sha256",
    "receipt_sha256",
    "gate_sha256",
    "stage_tree_sha256",
    "manifest_file_sha256",
    "stage_root",
    "deploy_root",
    "backup_root",
    "issued_at",
    "expires_at",
    "confirmation_contract_sha256",
}


def _parse_timestamp(value: Any) -> float | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    timestamp = parsed.astimezone(UTC).timestamp()
    return timestamp if math.isfinite(timestamp) else None


def confirmation_contract_sha256() -> str:
    """Identify the guarded upgrader's human confirmation contract."""

    return hashlib.sha256(PROMOTION_CONFIRMATION.encode("utf-8")).hexdigest()


def issue_final_handoff_seal(
    *,
    seal_id: str,
    request: Mapping[str, Any],
    receipt: Mapping[str, Any],
    gate: Mapping[str, Any],
    issued_at: str,
    expires_at: str,
) -> dict[str, Any]:
    """Issue a transient seal only for a currently pristine reviewed stage."""

    issued = _parse_timestamp(issued_at)
    expires = _parse_timestamp(expires_at)
    if (
        not isinstance(seal_id, str)
        or len(seal_id) < 24
        or gate.get("status") != "READY_FOR_MANUAL_PROMOTION"
        or gate.get("request_sha256") != semantic_sha256(request)
        or gate.get("receipt_sha256") != semantic_sha256(receipt)
        or issued is None
        or expires is None
        or expires <= issued
        or expires - issued > MAX_HANDOFF_LIFETIME_SECONDS
    ):
        raise ValueError("HandoffSealPrerequisiteFailed")

    witness = witness_validated_stage(str(request.get("stage_root") or ""))
    manifest = witness.get("manifest")
    if (
        witness.get("status") != "WITNESSED"
        or not isinstance(manifest, Mapping)
        or request.get("stage_tree_sha256") != witness.get("stage_tree_sha256")
        or request.get("stage_manifest_sha256") != semantic_sha256(manifest)
        or request.get("stage_root") != manifest.get("stage_root")
        or request.get("deploy_root") != manifest.get("deploy_root")
    ):
        raise ValueError("HandoffStageNotCurrent")

    return {
        "schema": HANDOFF_SEAL_SCHEMA,
        "seal_id": seal_id,
        "request_sha256": semantic_sha256(request),
        "receipt_sha256": semantic_sha256(receipt),
        "gate_sha256": semantic_sha256(gate),
        "stage_tree_sha256": witness["stage_tree_sha256"],
        "manifest_file_sha256": witness["manifest_sha256"],
        "stage_root": request.get("stage_root"),
        "deploy_root": request.get("deploy_root"),
        "backup_root": request.get("backup_root"),
        "issued_at": issued_at,
        "expires_at": expires_at,
        "confirmation_contract_sha256": confirmation_contract_sha256(),
    }


def evaluate_final_handoff(
    *,
    seal: Mapping[str, Any],
    request: Mapping[str, Any],
    receipt: Mapping[str, Any],
    gate: Mapping[str, Any],
    observed_at: str,
    consumed_seals: Sequence[str] = (),
) -> dict[str, Any]:
    """Re-witness the stage and decide whether a human may confirm promotion."""

    conditions: list[dict[str, Any]] = []

    def add(name: str, passed: bool, success: str, failure: str) -> None:
        conditions.append(
            {
                "condition": name,
                "passed": bool(passed),
                "reason": success if passed else failure,
            }
        )

    exact_fields = set(seal) == _SEAL_FIELDS
    add("sealed_fields", exact_fields, "SealFieldsExact", "SealFieldsUnexpected")
    add(
        "seal_schema",
        seal.get("schema") == HANDOFF_SEAL_SCHEMA,
        "SealSchemaMatched",
        "SealSchemaInvalid",
    )
    request_digest = semantic_sha256(request)
    receipt_digest = semantic_sha256(receipt)
    add(
        "request_binding",
        seal.get("request_sha256") == request_digest
        and gate.get("request_sha256") == request_digest,
        "RequestBound",
        "RequestDigestMismatch",
    )
    add(
        "receipt_binding",
        seal.get("receipt_sha256") == receipt_digest
        and gate.get("receipt_sha256") == receipt_digest,
        "ReceiptBound",
        "ReceiptDigestMismatch",
    )
    add(
        "gate_decision",
        gate.get("status") == "READY_FOR_MANUAL_PROMOTION",
        "ManualGateReady",
        "ManualGateHold",
    )
    add(
        "gate_binding",
        seal.get("gate_sha256") == semantic_sha256(gate),
        "ManualGateBound",
        "ManualGateDigestMismatch",
    )

    issued = _parse_timestamp(seal.get("issued_at"))
    expires = _parse_timestamp(seal.get("expires_at"))
    observed = _parse_timestamp(observed_at)
    lifetime_ok = (
        issued is not None
        and expires is not None
        and expires > issued
        and expires - issued <= MAX_HANDOFF_LIFETIME_SECONDS
    )
    add("bounded_lifetime", lifetime_ok, "SealLifetimeBounded", "SealLifetimeInvalid")
    clock_ok = observed is not None and issued is not None and observed >= issued
    add("clock_order", clock_ok, "ClockOrderValid", "ClockRollbackDetected")
    fresh = observed is not None and expires is not None and observed < expires
    add("seal_freshness", fresh, "SealFresh", "SealExpired")
    seal_digest = semantic_sha256(seal)
    unused = seal_digest not in set(consumed_seals)
    add("seal_not_replayed", unused, "SealUnused", "SealAlreadyConsumed")
    add(
        "confirmation_contract",
        seal.get("confirmation_contract_sha256") == confirmation_contract_sha256(),
        "ConfirmationContractBound",
        "ConfirmationContractMismatch",
    )

    witness = witness_validated_stage(str(request.get("stage_root") or ""))
    manifest = witness.get("manifest")
    witnessed = witness.get("status") == "WITNESSED" and isinstance(manifest, Mapping)
    add("current_stage_witness", witnessed, "StageRewitnessed", "StageWitnessHold")
    tree_bound = witnessed and (
        seal.get("stage_tree_sha256")
        == request.get("stage_tree_sha256")
        == witness.get("stage_tree_sha256")
    )
    add("current_stage_tree", tree_bound, "StageTreeCurrent", "StageTreeChanged")
    manifest_bound = witnessed and (
        seal.get("manifest_file_sha256") == witness.get("manifest_sha256")
        and request.get("stage_manifest_sha256") == semantic_sha256(manifest)
    )
    add("current_manifest", manifest_bound, "ManifestCurrent", "ManifestChanged")
    paths_bound = witnessed and (
        seal.get("stage_root")
        == request.get("stage_root")
        == manifest.get("stage_root")
        and seal.get("deploy_root")
        == request.get("deploy_root")
        == manifest.get("deploy_root")
        and seal.get("backup_root") == request.get("backup_root")
    )
    add("promotion_paths", paths_bound, "PromotionPathsBound", "PromotionPathsChanged")

    failed = [item for item in conditions if not item["passed"]]
    return {
        "schema": HANDOFF_DECISION_SCHEMA,
        "status": "READY_FOR_OPERATOR_CONFIRMATION" if not failed else "HOLD",
        "reason": "FinalHandoffChecksPassed" if not failed else failed[0]["reason"],
        "conditions": conditions,
        "seal_sha256": seal_digest,
        "witness_status": witness.get("status"),
        "requires_separate_human_confirmation": True,
        "confirmation_supplied": False,
        "seal_consumed": False,
        "promotion_performed": False,
        "services_modified": False,
        "runtime_writes": 0,
        "production_mutation": False,
        "control_authority": False,
    }


__all__ = [
    "HANDOFF_DECISION_SCHEMA",
    "HANDOFF_SEAL_SCHEMA",
    "MAX_HANDOFF_LIFETIME_SECONDS",
    "confirmation_contract_sha256",
    "evaluate_final_handoff",
    "issue_final_handoff_seal",
]
