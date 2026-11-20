"""Append-only transparency receipt gate for timestamped custody evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final

from .rfc4998_timestamped_custody import SCHEMA as TIMESTAMPED_SCHEMA
from .rfc4998_timestamped_custody import STATUS_TIMESTAMPED

SCHEMA: Final = "truepanel.aegis-rfc4998-transparent-custody/v1"
CHECKPOINT_SCHEMA: Final = "truepanel.aegis-transparency-checkpoint/v1"
STATUS_TRANSPARENT: Final = "APPEND_ONLY_CUSTODY_REHEARSED"
STATUS_RECEIPT_REQUIRED: Final = "ACTION_REQUIRED_TRANSPARENCY_RECEIPT"
STATUS_HOLD: Final = "HOLD"
NAMESPACE: Final = "truepanel-aegis-transparency-checkpoint-v1@truepanel"
KEY_ID: Final = "aegis-transparency-log@holodeck.invalid"

_DENIED: Final = (
    "production_trusted",
    "runtime_authority",
    "deployment_authority",
    "hardware_authority",
    "network_authority",
    "storage_authority",
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash_leaf(value: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + value).digest()


def _hash_node(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def _split(size: int) -> int:
    if size < 2:
        raise ValueError("TransparencyTreeTooSmall")
    return 1 << ((size - 1).bit_length() - 1)


def merkle_root(leaves: Sequence[bytes]) -> bytes:
    """Return the RFC 9162 Merkle Tree Hash for ordered leaves."""

    if not leaves:
        return hashlib.sha256(b"").digest()
    if len(leaves) == 1:
        return _hash_leaf(leaves[0])
    split = _split(len(leaves))
    return _hash_node(merkle_root(leaves[:split]), merkle_root(leaves[split:]))


def inclusion_proof(index: int, leaves: Sequence[bytes]) -> list[bytes]:
    if index < 0 or index >= len(leaves):
        raise ValueError("TransparencyLeafIndexInvalid")
    if len(leaves) == 1:
        return []
    split = _split(len(leaves))
    if index < split:
        return inclusion_proof(index, leaves[:split]) + [merkle_root(leaves[split:])]
    return inclusion_proof(index - split, leaves[split:]) + [
        merkle_root(leaves[:split])
    ]


def consistency_proof(first_size: int, leaves: Sequence[bytes]) -> list[bytes]:
    if first_size <= 0 or first_size > len(leaves):
        raise ValueError("TransparencyPriorTreeSizeInvalid")

    def subproof(size: int, values: Sequence[bytes], complete: bool) -> list[bytes]:
        if size == len(values):
            return [] if complete else [merkle_root(values)]
        split = _split(len(values))
        if size <= split:
            return subproof(size, values[:split], complete) + [
                merkle_root(values[split:])
            ]
        return subproof(size - split, values[split:], False) + [
            merkle_root(values[:split])
        ]

    return subproof(first_size, leaves, True)


def verify_inclusion(
    leaf: bytes,
    index: int,
    tree_size: int,
    proof: Sequence[bytes],
    expected_root: bytes,
) -> bool:
    if index < 0 or index >= tree_size or tree_size <= 0:
        return False
    cursor = 0

    def take() -> bytes:
        nonlocal cursor
        if cursor >= len(proof):
            raise ValueError("TransparencyInclusionPathShort")
        value = proof[cursor]
        cursor += 1
        return value

    def rebuild(position: int, size: int) -> bytes:
        if size == 1:
            return _hash_leaf(leaf)
        split = _split(size)
        if position < split:
            return _hash_node(rebuild(position, split), take())
        right = rebuild(position - split, size - split)
        return _hash_node(take(), right)

    try:
        actual = rebuild(index, tree_size)
    except ValueError:
        return False
    return cursor == len(proof) and actual == expected_root


def verify_consistency(
    first_size: int,
    second_size: int,
    first_root: bytes,
    second_root: bytes,
    proof: Sequence[bytes],
) -> bool:
    if first_size <= 0 or first_size > second_size:
        return False
    if first_size == second_size:
        return not proof and first_root == second_root
    path = list(proof)
    if first_size & (first_size - 1) == 0:
        path.insert(0, first_root)
    if not path:
        return False
    first_node = first_size - 1
    second_node = second_size - 1
    while first_node & 1:
        first_node >>= 1
        second_node >>= 1
    old_hash = new_hash = path[0]
    for node in path[1:]:
        if second_node == 0:
            return False
        if first_node & 1 or first_node == second_node:
            old_hash = _hash_node(node, old_hash)
            new_hash = _hash_node(node, new_hash)
            while first_node and not first_node & 1:
                first_node >>= 1
                second_node >>= 1
        else:
            new_hash = _hash_node(new_hash, node)
        first_node >>= 1
        second_node >>= 1
    return second_node == 0 and old_hash == first_root and new_hash == second_root


def build_transparency_entry(
    timestamped_custody: Mapping[str, Any], evidence: bytes
) -> bytes:
    return _canonical(
        {
            "schema": "truepanel.aegis-transparency-entry/v1",
            "record_id": timestamped_custody.get("record_id"),
            "custody_id": timestamped_custody.get("custody_id"),
            "timestamped_custody_record_sha256": timestamped_custody.get(
                "record_sha256"
            ),
            "timestamp_evidence_sha256": hashlib.sha256(evidence).hexdigest(),
            "authority": "NONE",
        }
    )


def evaluate_transparent_custody(
    timestamped_custody: Mapping[str, Any],
    evidence: bytes,
    receipt: Mapping[str, Any] | None,
    checkpoint_verifier: Callable[[str, bytes, str], bool] | None,
) -> dict[str, Any]:
    """Verify inclusion, append-only extension, and a signed checkpoint."""

    errors: list[str] = []
    if timestamped_custody.get("schema") != TIMESTAMPED_SCHEMA:
        errors.append("TimestampedCustodySchemaUnsupported")
    if timestamped_custody.get("status") != STATUS_TIMESTAMPED:
        errors.append("TimestampedCustodyRequired")
    if timestamped_custody.get("independent_signing_time_rehearsed") is not True:
        errors.append("IndependentSigningTimeRequired")
    if any(timestamped_custody.get(name) is not False for name in _DENIED):
        errors.append("TimestampedCustodyAuthorityEscalation")
    evidence_valid = isinstance(evidence, bytes) and bool(evidence)
    if not evidence_valid:
        errors.append("TimestampEvidenceInvalid")
    if receipt is not None and not isinstance(receipt, Mapping):
        errors.append("TransparencyReceiptInvalid")

    inclusion_ok = False
    consistency_ok = False
    checkpoint_ok = False
    entry = (
        build_transparency_entry(timestamped_custody, evidence)
        if evidence_valid
        else b""
    )
    if isinstance(receipt, Mapping) and not errors:
        try:
            if receipt.get("schema") != SCHEMA:
                raise ValueError("TransparencyReceiptSchemaUnsupported")
            checkpoint = receipt["checkpoint"]
            previous = receipt["previous_checkpoint"]
            if checkpoint.get("schema") != CHECKPOINT_SCHEMA:
                raise ValueError("TransparencyCheckpointSchemaUnsupported")
            if previous.get("schema") != CHECKPOINT_SCHEMA:
                raise ValueError("TransparencyPriorCheckpointSchemaUnsupported")
            if checkpoint.get("origin") != previous.get("origin"):
                raise ValueError("TransparencyOriginChanged")
            tree_size = int(checkpoint["tree_size"])
            prior_size = int(previous["tree_size"])
            index = int(receipt["leaf_index"])
            root = bytes.fromhex(checkpoint["root_hash_sha256"])
            prior_root = bytes.fromhex(previous["root_hash_sha256"])
            inclusion = [bytes.fromhex(value) for value in receipt["inclusion_path"]]
            consistency = [
                bytes.fromhex(value) for value in receipt["consistency_path"]
            ]
            if receipt.get("entry_sha256") != hashlib.sha256(entry).hexdigest():
                raise ValueError("TransparencyEntryMismatch")
            inclusion_ok = verify_inclusion(entry, index, tree_size, inclusion, root)
            if not inclusion_ok:
                raise ValueError("TransparencyInclusionInvalid")
            consistency_ok = verify_consistency(
                prior_size, tree_size, prior_root, root, consistency
            )
            if not consistency_ok:
                raise ValueError("TransparencyConsistencyInvalid")
            if checkpoint_verifier is None:
                raise ValueError("TransparencyCheckpointVerifierUnavailable")
            checkpoint_ok = checkpoint_verifier(
                str(receipt["log_key_id"]),
                _canonical(checkpoint),
                str(receipt["checkpoint_signature"]),
            ) and checkpoint_verifier(
                str(receipt["log_key_id"]),
                _canonical(previous),
                str(receipt["previous_checkpoint_signature"]),
            )
            if not checkpoint_ok:
                raise ValueError("TransparencyCheckpointSignatureInvalid")
        except (
            IndexError,
            KeyError,
            OSError,
            OverflowError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as error:
            errors.append(str(error))

    status = (
        STATUS_HOLD
        if errors
        else STATUS_RECEIPT_REQUIRED
        if receipt is None
        else STATUS_TRANSPARENT
    )
    result = {
        "schema": SCHEMA,
        "status": status,
        "record_id": timestamped_custody.get("record_id"),
        "custody_id": timestamped_custody.get("custody_id"),
        "timestamped_custody_record_sha256": timestamped_custody.get(
            "record_sha256"
        ),
        "transparency_entry_sha256": hashlib.sha256(entry).hexdigest() if entry else None,
        "checkpoint_signature_verified": checkpoint_ok,
        "inclusion_proof_verified": inclusion_ok,
        "append_only_consistency_verified": consistency_ok,
        "independent_monitor_required": True,
        "active_runtime_record_validation": "PENDING",
        "eligible_for_production_trust": False,
        "errors": list(dict.fromkeys(errors)),
        **{name: False for name in _DENIED},
    }
    result["record_sha256"] = hashlib.sha256(_canonical(result)).hexdigest()
    return result


__all__ = [
    "CHECKPOINT_SCHEMA",
    "KEY_ID",
    "NAMESPACE",
    "SCHEMA",
    "STATUS_HOLD",
    "STATUS_RECEIPT_REQUIRED",
    "STATUS_TRANSPARENT",
    "build_transparency_entry",
    "consistency_proof",
    "evaluate_transparent_custody",
    "inclusion_proof",
    "merkle_root",
    "verify_consistency",
    "verify_inclusion",
]
