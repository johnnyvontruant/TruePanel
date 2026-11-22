"""State-continuity gate for independently monitored transparency checkpoints."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final

from .rfc4998_transparent_custody import verify_consistency
from .transparency_monitor_quorum import MONITOR_IDS
from .transparency_monitor_quorum import SCHEMA as QUORUM_SCHEMA
from .transparency_monitor_quorum import STATUS_REHEARSED as QUORUM_REHEARSED

SCHEMA: Final = "truepanel.aegis-transparency-witness-continuity/v1"
TRANSITION_SCHEMA: Final = "truepanel.aegis-transparency-witness-transition/v1"
STATUS_REHEARSED: Final = "TRANSPARENCY_WITNESS_CONTINUITY_REHEARSED"
STATUS_HOLD: Final = "HOLD"
NAMESPACE: Final = "truepanel-aegis-witness-continuity-v1@truepanel"
QUORUM_THRESHOLD: Final = 2

_DENIED: Final = (
    "production_trusted", "runtime_authority", "deployment_authority",
    "hardware_authority", "network_authority", "storage_authority",
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def checkpoint_digest(checkpoint: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(checkpoint)).hexdigest()


def transition_statement(transition: Mapping[str, Any]) -> bytes:
    return _canonical({key: value for key, value in transition.items() if key != "signature"})


def evaluate_witness_continuity(
    monitor_quorum: Mapping[str, Any], prior_checkpoint: Mapping[str, Any],
    current_checkpoint: Mapping[str, Any],
    transitions: Sequence[Mapping[str, Any]] | None,
    verifier: Callable[[str, bytes, str], bool] | None, *,
    allowed_monitor_ids: Sequence[str] = MONITOR_IDS,
    threshold: int = QUORUM_THRESHOLD,
) -> dict[str, Any]:
    """Verify two monitor ratchets from exact persisted prior state."""
    errors: list[str] = []
    if monitor_quorum.get("schema") != QUORUM_SCHEMA:
        errors.append("MonitorQuorumSchemaUnsupported")
    if monitor_quorum.get("status") != QUORUM_REHEARSED:
        errors.append("MonitorQuorumRequired")
    if monitor_quorum.get("independent_monitor_quorum_rehearsed") is not True:
        errors.append("MonitorQuorumEvidenceRequired")
    if any(monitor_quorum.get(name) is not False for name in _DENIED):
        errors.append("MonitorQuorumAuthorityEscalation")

    allowed = tuple(allowed_monitor_ids)
    if threshold <= 0 or threshold > len(allowed):
        errors.append("WitnessContinuityPolicyInvalid")
    if len(set(allowed)) != len(allowed):
        errors.append("WitnessContinuityRosterDuplicateIdentity")
    if transitions is None:
        errors.append("WitnessTransitionsRequired")
        candidates: Sequence[Mapping[str, Any]] = ()
    elif not isinstance(transitions, Sequence) or isinstance(transitions, (str, bytes)):
        errors.append("WitnessTransitionsInvalid")
        candidates = ()
    else:
        candidates = transitions

    prior_digest = checkpoint_digest(prior_checkpoint)
    current_digest = checkpoint_digest(current_checkpoint)
    valid_ids: list[str] = []
    seen_ids: set[str] = set()
    states: set[tuple[str, int, str, int, str]] = set()
    for transition in candidates:
        try:
            if not isinstance(transition, Mapping):
                raise ValueError("WitnessTransitionInvalid")
            if transition.get("schema") != TRANSITION_SCHEMA:
                raise ValueError("WitnessTransitionSchemaUnsupported")
            monitor_id = str(transition["monitor_id"])
            if monitor_id in seen_ids:
                raise ValueError("WitnessTransitionDuplicateIdentity")
            seen_ids.add(monitor_id)
            if monitor_id not in allowed:
                raise ValueError("WitnessIdentityUntrusted")
            before = transition["state_before"]
            after = transition["state_after"]
            if not isinstance(before, Mapping) or not isinstance(after, Mapping):
                raise ValueError("WitnessStateInvalid")
            if before.get("monitor_id") != monitor_id or after.get("monitor_id") != monitor_id:
                raise ValueError("WitnessStateIdentityMismatch")
            if before.get("checkpoint_sha256") != prior_digest:
                raise ValueError("WitnessPriorCheckpointMismatch")
            if after.get("checkpoint_sha256") != current_digest:
                raise ValueError("WitnessCurrentCheckpointMismatch")
            old_size = int(before["tree_size"])
            new_size = int(after["tree_size"])
            old_root = str(before["root_hash_sha256"])
            new_root = str(after["root_hash_sha256"])
            before_sequence = int(before["state_sequence"])
            after_sequence = int(after["state_sequence"])
            states.add((str(before["origin"]), old_size, old_root, new_size, new_root))
            if before.get("origin") != prior_checkpoint.get("origin") or after.get("origin") != current_checkpoint.get("origin"):
                raise ValueError("WitnessCheckpointOriginMismatch")
            if old_size != int(prior_checkpoint["tree_size"]):
                raise ValueError("WitnessOldSizeStale")
            if new_size != int(current_checkpoint["tree_size"]):
                raise ValueError("WitnessNewSizeMismatch")
            if new_size < old_size:
                raise ValueError("WitnessTreeRewind")
            if old_root != prior_checkpoint.get("root_hash_sha256"):
                raise ValueError("WitnessPriorRootMismatch")
            if new_root != current_checkpoint.get("root_hash_sha256"):
                raise ValueError("WitnessCurrentRootMismatch")
            if before_sequence < 1 or after_sequence != before_sequence + 1:
                raise ValueError("WitnessStateSequenceInvalid")
            if transition.get("persisted_before_cosignature") is not True:
                raise ValueError("WitnessPersistenceOrderingInvalid")
            proof = [bytes.fromhex(value) for value in transition["consistency_path"]]
            if not verify_consistency(old_size, new_size, bytes.fromhex(old_root), bytes.fromhex(new_root), proof):
                raise ValueError("WitnessConsistencyProofInvalid")
            if verifier is None:
                raise ValueError("WitnessContinuityVerifierUnavailable")
            if not verifier(monitor_id, transition_statement(transition), str(transition["signature"])):
                raise ValueError("WitnessContinuitySignatureInvalid")
            valid_ids.append(monitor_id)
        except (KeyError, OSError, OverflowError, RuntimeError, TypeError, ValueError) as error:
            errors.append(str(error) or error.__class__.__name__)

    if len(states) > 1:
        errors.append("WitnessStateForkDetected")
    if len(valid_ids) < threshold:
        errors.append("WitnessContinuityQuorumNotMet")
    status = STATUS_REHEARSED if not errors else STATUS_HOLD
    result = {
        "schema": SCHEMA, "status": status,
        "prior_checkpoint_sha256": prior_digest,
        "current_checkpoint_sha256": current_digest,
        "quorum_threshold": threshold, "valid_monitor_count": len(valid_ids),
        "valid_monitor_ids": sorted(valid_ids), "state_fork_detected": len(states) > 1,
        "atomic_persistence_rehearsed": status == STATUS_REHEARSED,
        "witness_state_continuity_rehearsed": status == STATUS_REHEARSED,
        "monitor_operator_independence": "SIMULATED_NOT_PRODUCTION_PROVEN",
        "active_runtime_record_validation": "PENDING",
        "eligible_for_production_trust": False,
        "errors": list(dict.fromkeys(errors)), **{name: False for name in _DENIED},
    }
    result["record_sha256"] = hashlib.sha256(_canonical(result)).hexdigest()
    return result


__all__ = ["NAMESPACE", "SCHEMA", "STATUS_HOLD", "STATUS_REHEARSED", "TRANSITION_SCHEMA", "checkpoint_digest", "evaluate_witness_continuity", "transition_statement"]
