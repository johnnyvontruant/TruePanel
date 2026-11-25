"""Anchored recovery policy for deterministic witness storage-fault rehearsal."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from .transparency_witness_crash_recovery import WitnessStateError, _digest
from .transparency_witness_sqlite_recovery import (
    SQLiteWitnessDurableStateStore,
    evaluate_isolated_witness_stores,
)

ANCHOR_SCHEMA: Final = "truepanel.aegis-witness-recovery-anchor/v1"
SCHEMA: Final = "truepanel.aegis-witness-storage-fault-recovery/v1"
STATUS_REHEARSED: Final = "ANCHORED_WITNESS_STORAGE_FAULT_RECOVERY_REHEARSED"
STATUS_HOLD: Final = "ANCHORED_WITNESS_STORAGE_FAULT_RECOVERY_HOLD"
_DENIED: Final = (
    "production_trusted",
    "runtime_authority",
    "deployment_authority",
    "hardware_authority",
    "network_authority",
    "storage_authority",
)


def create_recovery_anchor(
    stores: Sequence[SQLiteWitnessDurableStateStore],
) -> dict[str, Any]:
    """Bind the exact two-store recovery point reviewed before a fault."""
    quorum = evaluate_isolated_witness_stores(stores)
    if quorum.get("status") != "ISOLATED_WITNESS_SQLITE_RECOVERY_REHEARSED":
        raise WitnessStateError("WitnessRecoveryAnchorRequiresHealthyQuorum")
    observations = quorum["stores"]
    checkpoint = observations[0]["checkpoint_sha256"]
    sequence = observations[0]["state_sequence"]
    anchor: dict[str, Any] = {
        "schema": ANCHOR_SCHEMA,
        "checkpoint_sha256": checkpoint,
        "state_sequence": sequence,
        "monitor_record_sha256": {
            item["monitor_id"]: item["record_sha256"] for item in observations
        },
        "source_quorum_result_sha256": quorum["result_sha256"],
        "physical_power_loss_validated": False,
        **{name: False for name in _DENIED},
    }
    anchor["anchor_sha256"] = _digest(anchor)
    return anchor


def evaluate_anchored_witness_recovery(
    stores: Sequence[SQLiteWitnessDurableStateStore],
    anchor: Mapping[str, Any],
) -> dict[str, Any]:
    """Fail closed unless both recovered stores match the reviewed anchor."""
    errors: list[str] = []
    if anchor.get("schema") != ANCHOR_SCHEMA:
        errors.append("WitnessRecoveryAnchorSchemaUnsupported")
    expected_digest = anchor.get("anchor_sha256")
    anchor_payload = {key: value for key, value in anchor.items() if key != "anchor_sha256"}
    if not isinstance(expected_digest, str) or expected_digest != _digest(anchor_payload):
        errors.append("WitnessRecoveryAnchorDigestMismatch")
    if any(anchor.get(name) is not False for name in _DENIED):
        errors.append("WitnessRecoveryAnchorAuthorityEscalation")

    quorum = evaluate_isolated_witness_stores(stores)
    if quorum.get("status") != "ISOLATED_WITNESS_SQLITE_RECOVERY_REHEARSED":
        errors.extend(quorum.get("errors", ()))
        errors.append("WitnessRecoveryQuorumUnavailable")

    expected_records = anchor.get("monitor_record_sha256")
    if not isinstance(expected_records, Mapping) or len(expected_records) != 2:
        errors.append("WitnessRecoveryAnchorRecordsInvalid")
        expected_records = {}
    for observation in quorum.get("stores", ()):
        monitor_id = observation.get("monitor_id")
        if observation.get("checkpoint_sha256") != anchor.get("checkpoint_sha256"):
            errors.append("WitnessRecoveryCheckpointRollbackOrFork")
        if observation.get("state_sequence") != anchor.get("state_sequence"):
            errors.append("WitnessRecoverySequenceRollbackOrFork")
        if expected_records.get(monitor_id) != observation.get("record_sha256"):
            errors.append("WitnessRecoveryRecordSubstitution")

    status = STATUS_REHEARSED if not errors else STATUS_HOLD
    result = {
        "schema": SCHEMA,
        "status": status,
        "anchor_sha256": expected_digest,
        "recovered_store_count": quorum.get("store_count", 0),
        "checkpoint_agreement": quorum.get("checkpoint_agreement", False),
        "exact_anchor_match": status == STATUS_REHEARSED,
        "deterministic_storage_fault_rehearsal": True,
        "physical_power_loss_validated": False,
        "independent_production_monitor_operators": 0,
        "eligible_for_production_trust": False,
        "errors": list(dict.fromkeys(errors)),
        **{name: False for name in _DENIED},
    }
    result["result_sha256"] = _digest(result)
    return result


__all__ = [
    "ANCHOR_SCHEMA",
    "SCHEMA",
    "STATUS_HOLD",
    "STATUS_REHEARSED",
    "create_recovery_anchor",
    "evaluate_anchored_witness_recovery",
]
