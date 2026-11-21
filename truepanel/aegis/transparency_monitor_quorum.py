"""Independent-monitor quorum gate for AEGIS transparency checkpoints."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final

from .rfc4998_transparent_custody import SCHEMA as TRANSPARENT_SCHEMA
from .rfc4998_transparent_custody import STATUS_TRANSPARENT

SCHEMA: Final = "truepanel.aegis-transparency-monitor-quorum/v1"
OBSERVATION_SCHEMA: Final = "truepanel.aegis-transparency-monitor-observation/v1"
STATUS_REHEARSED: Final = "TRANSPARENCY_MONITOR_QUORUM_REHEARSED"
STATUS_HOLD: Final = "HOLD"
NAMESPACE: Final = "truepanel-aegis-transparency-monitor-v1@truepanel"
MONITOR_IDS: Final = ("aegis-monitor-alpha@holodeck.invalid", "aegis-monitor-bravo@holodeck.invalid")
QUORUM_THRESHOLD: Final = 2
_DENIED: Final = ("production_trusted", "runtime_authority", "deployment_authority", "hardware_authority", "network_authority", "storage_authority")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def checkpoint_digest(checkpoint: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(checkpoint)).hexdigest()


def observation_statement(observation: Mapping[str, Any]) -> bytes:
    return _canonical({key: value for key, value in observation.items() if key != "signature"})


def evaluate_monitor_quorum(
    transparent_custody: Mapping[str, Any], checkpoint: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]] | None,
    verifier: Callable[[str, bytes, str], bool] | None, *,
    allowed_monitor_ids: Sequence[str] = MONITOR_IDS, threshold: int = QUORUM_THRESHOLD,
) -> dict[str, Any]:
    """Require distinct trusted monitors to countersign one exact checkpoint."""
    errors: list[str] = []
    if transparent_custody.get("schema") != TRANSPARENT_SCHEMA:
        errors.append("TransparentCustodySchemaUnsupported")
    if transparent_custody.get("status") != STATUS_TRANSPARENT:
        errors.append("TransparentCustodyRequired")
    if transparent_custody.get("checkpoint_signature_verified") is not True:
        errors.append("SignedCheckpointRequired")
    if transparent_custody.get("append_only_consistency_verified") is not True:
        errors.append("AppendOnlyConsistencyRequired")
    if transparent_custody.get("inclusion_proof_verified") is not True:
        errors.append("InclusionProofRequired")
    if any(transparent_custody.get(name) is not False for name in _DENIED):
        errors.append("TransparentCustodyAuthorityEscalation")
    allowed = tuple(allowed_monitor_ids)
    if threshold <= 0 or threshold > len(allowed):
        errors.append("MonitorQuorumPolicyInvalid")
    if len(set(allowed)) != len(allowed):
        errors.append("MonitorRosterDuplicateIdentity")
    if observations is None:
        errors.append("MonitorObservationsRequired")
        candidates: Sequence[Mapping[str, Any]] = ()
    elif not isinstance(observations, Sequence) or isinstance(observations, (str, bytes)):
        errors.append("MonitorObservationsInvalid")
        candidates = ()
    else:
        candidates = observations
    expected_digest = checkpoint_digest(checkpoint)
    valid_ids: list[str] = []
    seen_ids: set[str] = set()
    views: set[tuple[str, int, str]] = set()
    for observation in candidates:
        try:
            if not isinstance(observation, Mapping):
                raise ValueError("MonitorObservationInvalid")
            if observation.get("schema") != OBSERVATION_SCHEMA:
                raise ValueError("MonitorObservationSchemaUnsupported")
            monitor_id = str(observation["monitor_id"])
            if monitor_id in seen_ids:
                raise ValueError("MonitorObservationDuplicateIdentity")
            seen_ids.add(monitor_id)
            if monitor_id not in allowed:
                raise ValueError("MonitorIdentityUntrusted")
            origin = str(observation["origin"])
            tree_size = int(observation["tree_size"])
            root_hash = str(observation["root_hash_sha256"])
            views.add((origin, tree_size, root_hash))
            if observation.get("checkpoint_sha256") != expected_digest:
                raise ValueError("MonitorCheckpointDigestMismatch")
            if origin != checkpoint.get("origin"):
                raise ValueError("MonitorCheckpointOriginMismatch")
            if tree_size != int(checkpoint["tree_size"]):
                raise ValueError("MonitorCheckpointSizeMismatch")
            if root_hash != checkpoint.get("root_hash_sha256"):
                raise ValueError("MonitorCheckpointRootMismatch")
            if verifier is None:
                raise ValueError("MonitorVerifierUnavailable")
            if not verifier(monitor_id, observation_statement(observation), str(observation["signature"])):
                raise ValueError("MonitorSignatureInvalid")
            valid_ids.append(monitor_id)
        except (KeyError, OSError, OverflowError, RuntimeError, TypeError, ValueError) as error:
            errors.append(str(error) or error.__class__.__name__)
    if len(views) > 1:
        errors.append("MonitorSplitViewDetected")
    if len(valid_ids) < threshold:
        errors.append("MonitorQuorumNotMet")
    status = STATUS_REHEARSED if not errors else STATUS_HOLD
    result = {
        "schema": SCHEMA, "status": status, "checkpoint_sha256": expected_digest,
        "quorum_threshold": threshold, "valid_monitor_count": len(valid_ids),
        "valid_monitor_ids": sorted(valid_ids), "split_view_detected": len(views) > 1,
        "independent_monitor_quorum_rehearsed": status == STATUS_REHEARSED,
        "monitor_operator_independence": "SIMULATED_NOT_PRODUCTION_PROVEN",
        "active_runtime_record_validation": "PENDING", "eligible_for_production_trust": False,
        "errors": list(dict.fromkeys(errors)), **{name: False for name in _DENIED},
    }
    result["record_sha256"] = hashlib.sha256(_canonical(result)).hexdigest()
    return result


__all__ = ["MONITOR_IDS", "NAMESPACE", "OBSERVATION_SCHEMA", "QUORUM_THRESHOLD", "SCHEMA", "STATUS_HOLD", "STATUS_REHEARSED", "checkpoint_digest", "evaluate_monitor_quorum", "observation_statement"]
