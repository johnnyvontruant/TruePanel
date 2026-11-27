"""Dual-threshold rotation policy for witness-anchor custodians."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final

from .transparency_witness_anchor_custody import (
    CUSTODIAN_IDS as CURRENT_CUSTODIAN_IDS,
)
from .transparency_witness_anchor_custody import (
    anchor_custody_statement_bytes,
)

ROOT_SCHEMA: Final = "truepanel.aegis-witness-anchor-custodian-root/v1"
SCHEMA: Final = "truepanel.aegis-witness-anchor-custodian-rotation/v1"
STATEMENT_TYPE: Final = "https://in-toto.io/Statement/v1"
PREDICATE_TYPE: Final = (
    "https://truepanel.dev/attestations/aegis-witness-anchor-custodian-rotation/v1"
)
NAMESPACE: Final = "truepanel-aegis-witness-anchor-root-rotation-v1@truepanel"
NEXT_CUSTODIAN_IDS: Final = (
    CURRENT_CUSTODIAN_IDS[1],
    "aegis-anchor-custodian-charlie@holodeck.invalid",
)
THRESHOLD: Final = 2
STATUS_REHEARSED: Final = "DUAL_THRESHOLD_CUSTODIAN_ROTATION_REHEARSED"
STATUS_HOLD: Final = "DUAL_THRESHOLD_CUSTODIAN_ROTATION_HOLD"
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


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _validate_fingerprints(
    fingerprints: Mapping[str, str], expected_ids: Sequence[str]
) -> None:
    expected = tuple(expected_ids)
    if (
        set(fingerprints) != set(expected)
        or len(set(expected)) != len(expected)
        or any(
            not isinstance(value, str) or not value.startswith("SHA256:")
            for value in fingerprints.values()
        )
        or len(set(fingerprints.values())) != len(expected)
    ):
        raise ValueError("WitnessAnchorRotationCustodianRootInvalid")


def build_custodian_root(
    *,
    version: int,
    anchor_statement: Mapping[str, Any],
    custodian_fingerprints: Mapping[str, str],
    custodian_ids: Sequence[str],
    predecessor_root_sha256: str | None,
    custody_evidence_sha256: str,
    threshold: int = THRESHOLD,
) -> dict[str, Any]:
    """Build one content-addressed offline custodian trust root."""
    ids = tuple(custodian_ids)
    _validate_fingerprints(custodian_fingerprints, ids)
    if (
        not isinstance(version, int)
        or isinstance(version, bool)
        or version < 1
        or threshold != THRESHOLD
        or threshold > len(ids)
        or not isinstance(custody_evidence_sha256, str)
        or len(custody_evidence_sha256) != 64
        or (version == 1) != (predecessor_root_sha256 is None)
        or (
            predecessor_root_sha256 is not None
            and (
                not isinstance(predecessor_root_sha256, str)
                or len(predecessor_root_sha256) != 64
            )
        )
    ):
        raise ValueError("WitnessAnchorRotationCustodianRootInvalid")
    payload = {
        "schema": ROOT_SCHEMA,
        "version": version,
        "anchor_statement_sha256": hashlib.sha256(
            anchor_custody_statement_bytes(anchor_statement)
        ).hexdigest(),
        "custody_evidence_sha256": custody_evidence_sha256,
        "predecessor_root_sha256": predecessor_root_sha256,
        "custodian_fingerprints": {
            key: custodian_fingerprints[key] for key in sorted(custodian_fingerprints)
        },
        "threshold": threshold,
        **{name: False for name in _DENIED},
    }
    return {**payload, "root_sha256": _digest(payload)}


def build_rotation_statement(
    current_root: Mapping[str, Any], next_root: Mapping[str, Any]
) -> dict[str, Any]:
    """Bind an exact N to N+1 root transition to both threshold policies."""
    return {
        "_type": STATEMENT_TYPE,
        "subject": [
            {
                "name": "truepanel-witness-anchor-custodian-root.json",
                "digest": {"sha256": next_root["root_sha256"]},
            }
        ],
        "predicateType": PREDICATE_TYPE,
        "predicate": {
            "schema": SCHEMA,
            "namespace": NAMESPACE,
            "current_root_sha256": current_root["root_sha256"],
            "current_version": current_root["version"],
            "next_version": next_root["version"],
            "anchor_statement_sha256": next_root["anchor_statement_sha256"],
            "custody_evidence_sha256": next_root["custody_evidence_sha256"],
            "current_threshold": current_root["threshold"],
            "next_threshold": next_root["threshold"],
            "dual_threshold_required": True,
            "physical_operator_independence": "SIMULATED_NOT_PRODUCTION_PROVEN",
            **{name: False for name in _DENIED},
        },
    }


def rotation_statement_bytes(statement: Mapping[str, Any]) -> bytes:
    return _canonical(statement)


def _root_errors(
    root: Mapping[str, Any], expected_ids: Sequence[str], label: str
) -> list[str]:
    errors: list[str] = []
    payload = {key: value for key, value in root.items() if key != "root_sha256"}
    if (
        root.get("schema") != ROOT_SCHEMA
        or root.get("root_sha256") != _digest(payload)
        or root.get("threshold") != THRESHOLD
        or any(root.get(name) is not False for name in _DENIED)
    ):
        errors.append(f"WitnessAnchorRotation{label}RootInvalid")
    fingerprints = root.get("custodian_fingerprints")
    try:
        if not isinstance(fingerprints, Mapping):
            raise ValueError
        _validate_fingerprints(fingerprints, expected_ids)
    except (TypeError, ValueError):
        errors.append(f"WitnessAnchorRotation{label}RosterInvalid")
    return errors


def _verify_threshold(
    *,
    signatures: Sequence[Mapping[str, Any]] | None,
    allowed_ids: Sequence[str],
    statement_bytes: bytes,
    verifier: Callable[[str, bytes, str], bool] | None,
    label: str,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    valid: list[str] = []
    if (
        signatures is None
        or not isinstance(signatures, Sequence)
        or isinstance(signatures, (str, bytes))
    ):
        return valid, [f"WitnessAnchorRotation{label}SignaturesRequired"]
    seen: set[str] = set()
    allowed = set(allowed_ids)
    for item in signatures:
        try:
            if not isinstance(item, Mapping):
                raise ValueError(f"WitnessAnchorRotation{label}SignatureInvalid")
            identity = str(item["custodian_id"])
            signature = str(item["signature"])
            if identity in seen:
                raise ValueError(f"WitnessAnchorRotation{label}DuplicateIdentity")
            seen.add(identity)
            if identity not in allowed:
                raise ValueError(f"WitnessAnchorRotation{label}IdentityUntrusted")
            if verifier is None or not verifier(identity, statement_bytes, signature):
                raise ValueError(f"WitnessAnchorRotation{label}SignatureInvalid")
            valid.append(identity)
        except (KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
            errors.append(str(error) or error.__class__.__name__)
    if len(valid) < THRESHOLD:
        errors.append(f"WitnessAnchorRotation{label}ThresholdNotMet")
    return valid, errors


def evaluate_custodian_root_rotation(
    current_root: Mapping[str, Any],
    next_root: Mapping[str, Any],
    anchor_statement: Mapping[str, Any],
    custody_evidence_sha256: str,
    rotation_statement: Mapping[str, Any],
    current_signatures: Sequence[Mapping[str, Any]] | None,
    next_signatures: Sequence[Mapping[str, Any]] | None,
    current_verifier: Callable[[str, bytes, str], bool] | None,
    next_verifier: Callable[[str, bytes, str], bool] | None,
    *,
    current_custodian_ids: Sequence[str] = CURRENT_CUSTODIAN_IDS,
    next_custodian_ids: Sequence[str] = NEXT_CUSTODIAN_IDS,
) -> dict[str, Any]:
    """Require old and new 2-of-2 approval for one exact root rotation."""
    errors = _root_errors(current_root, current_custodian_ids, "Current")
    errors.extend(_root_errors(next_root, next_custodian_ids, "Next"))
    if tuple(current_custodian_ids) != CURRENT_CUSTODIAN_IDS:
        errors.append("WitnessAnchorRotationCurrentPolicyMismatch")
    if tuple(next_custodian_ids) != NEXT_CUSTODIAN_IDS:
        errors.append("WitnessAnchorRotationNextPolicyMismatch")
    current_version = current_root.get("version")
    next_version = next_root.get("version")
    if (
        not isinstance(current_version, int)
        or isinstance(current_version, bool)
        or not isinstance(next_version, int)
        or isinstance(next_version, bool)
        or next_version != current_version + 1
    ):
        errors.append("WitnessAnchorRotationVersionNotConsecutive")
    if next_root.get("predecessor_root_sha256") != current_root.get("root_sha256"):
        errors.append("WitnessAnchorRotationPredecessorMismatch")
    statement_digest = hashlib.sha256(
        anchor_custody_statement_bytes(anchor_statement)
    ).hexdigest()
    if (
        current_root.get("anchor_statement_sha256") != statement_digest
        or next_root.get("anchor_statement_sha256") != statement_digest
    ):
        errors.append("WitnessAnchorRotationAnchorStatementMismatch")
    if (
        not isinstance(custody_evidence_sha256, str)
        or len(custody_evidence_sha256) != 64
        or current_root.get("custody_evidence_sha256") != custody_evidence_sha256
        or next_root.get("custody_evidence_sha256") != custody_evidence_sha256
    ):
        errors.append("WitnessAnchorRotationCustodyEvidenceMismatch")
    if current_root.get("custodian_fingerprints") == next_root.get(
        "custodian_fingerprints"
    ):
        errors.append("WitnessAnchorRotationNoKeyChange")
    expected_statement: dict[str, Any] | None = None
    try:
        expected_statement = build_rotation_statement(current_root, next_root)
    except (KeyError, TypeError, ValueError) as error:
        errors.append(str(error) or error.__class__.__name__)
    if expected_statement is None or dict(rotation_statement) != expected_statement:
        errors.append("WitnessAnchorRotationStatementMismatch")
    predicate = rotation_statement.get("predicate")
    if not isinstance(predicate, Mapping) or any(
        predicate.get(name) is not False for name in _DENIED
    ):
        errors.append("WitnessAnchorRotationAuthorityEscalation")

    signed_bytes = _canonical(rotation_statement)
    current_valid, current_errors = _verify_threshold(
        signatures=current_signatures,
        allowed_ids=current_custodian_ids,
        statement_bytes=signed_bytes,
        verifier=current_verifier,
        label="Current",
    )
    next_valid, next_errors = _verify_threshold(
        signatures=next_signatures,
        allowed_ids=next_custodian_ids,
        statement_bytes=signed_bytes,
        verifier=next_verifier,
        label="Next",
    )
    errors.extend(current_errors)
    errors.extend(next_errors)
    status = STATUS_REHEARSED if not errors else STATUS_HOLD
    result = {
        "schema": SCHEMA,
        "status": status,
        "current_root_sha256": current_root.get("root_sha256"),
        "next_root_sha256": next_root.get("root_sha256"),
        "rotation_statement_sha256": hashlib.sha256(signed_bytes).hexdigest(),
        "current_version": current_version,
        "next_version": next_version,
        "current_valid_custodian_ids": sorted(current_valid),
        "next_valid_custodian_ids": sorted(next_valid),
        "current_threshold_verified": len(set(current_valid)) >= THRESHOLD,
        "next_threshold_verified": len(set(next_valid)) >= THRESHOLD,
        "eligible_for_production_trust": False,
        "physical_operator_independence": "SIMULATED_NOT_PRODUCTION_PROVEN",
        "physical_power_loss_validated": False,
        "errors": list(dict.fromkeys(errors)),
        **{name: False for name in _DENIED},
    }
    result["result_sha256"] = _digest(result)
    return result


__all__ = [
    "CURRENT_CUSTODIAN_IDS",
    "NAMESPACE",
    "NEXT_CUSTODIAN_IDS",
    "ROOT_SCHEMA",
    "SCHEMA",
    "STATUS_HOLD",
    "STATUS_REHEARSED",
    "THRESHOLD",
    "build_custodian_root",
    "build_rotation_statement",
    "evaluate_custodian_root_rotation",
    "rotation_statement_bytes",
]
