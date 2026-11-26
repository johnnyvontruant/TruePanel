"""Threshold custody policy for an offline witness recovery anchor."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final

from .transparency_witness_sqlite_recovery import SQLiteWitnessDurableStateStore
from .transparency_witness_storage_faults import (
    ANCHOR_SCHEMA,
    evaluate_anchored_witness_recovery,
)
from .transparency_witness_storage_faults import (
    STATUS_REHEARSED as STORAGE_RECOVERY_REHEARSED,
)

SCHEMA: Final = "truepanel.aegis-witness-anchor-threshold-custody/v1"
STATEMENT_TYPE: Final = "https://in-toto.io/Statement/v1"
PREDICATE_TYPE: Final = (
    "https://truepanel.dev/attestations/aegis-witness-anchor-custody/v1"
)
NAMESPACE: Final = "truepanel-aegis-witness-anchor-custody-v1@truepanel"
CUSTODIAN_IDS: Final = (
    "aegis-anchor-custodian-alpha@holodeck.invalid",
    "aegis-anchor-custodian-bravo@holodeck.invalid",
)
THRESHOLD: Final = 2
STATUS_REHEARSED: Final = "THRESHOLD_ANCHOR_CUSTODY_REHEARSED"
STATUS_HOLD: Final = "THRESHOLD_ANCHOR_CUSTODY_HOLD"
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


def build_anchor_custody_statement(anchor: Mapping[str, Any]) -> dict[str, Any]:
    """Bind the exact content-addressed anchor to a narrow custody purpose."""
    anchor_digest = anchor.get("anchor_sha256")
    payload = {key: value for key, value in anchor.items() if key != "anchor_sha256"}
    if (
        anchor.get("schema") != ANCHOR_SCHEMA
        or not isinstance(anchor_digest, str)
        or len(anchor_digest) != 64
        or anchor_digest != hashlib.sha256(_canonical(payload)).hexdigest()
        or any(anchor.get(name) is not False for name in _DENIED)
    ):
        raise ValueError("WitnessAnchorCustodyAnchorInvalid")
    return {
        "_type": STATEMENT_TYPE,
        "subject": [
            {
                "name": "truepanel-witness-recovery-anchor.json",
                "digest": {"sha256": anchor_digest},
            }
        ],
        "predicateType": PREDICATE_TYPE,
        "predicate": {
            "schema": SCHEMA,
            "namespace": NAMESPACE,
            "anchor_schema": ANCHOR_SCHEMA,
            "checkpoint_sha256": anchor["checkpoint_sha256"],
            "state_sequence": anchor["state_sequence"],
            "threshold": THRESHOLD,
            "distinct_identities_required": True,
            "offline_custody_rehearsal": True,
            "physical_operator_independence": "SIMULATED_NOT_PRODUCTION_PROVEN",
            **{name: False for name in _DENIED},
        },
    }


def anchor_custody_statement_bytes(statement: Mapping[str, Any]) -> bytes:
    """Return the one canonical byte representation accepted for signatures."""
    return _canonical(statement)


def evaluate_threshold_anchor_custody(
    stores: Sequence[SQLiteWitnessDurableStateStore],
    anchor: Mapping[str, Any],
    statement: Mapping[str, Any],
    signatures: Sequence[Mapping[str, Any]] | None,
    verifier: Callable[[str, bytes, str], bool] | None,
    custodian_fingerprints: Mapping[str, str] | None,
    *,
    allowed_custodian_ids: Sequence[str] = CUSTODIAN_IDS,
    threshold: int = THRESHOLD,
) -> dict[str, Any]:
    """Require distinct governed signatures over the exact recovered anchor."""
    errors: list[str] = []
    recovery = evaluate_anchored_witness_recovery(stores, anchor)
    if recovery.get("status") != STORAGE_RECOVERY_REHEARSED:
        errors.append("WitnessAnchorCustodyRecoveryNotRehearsed")
        errors.extend(recovery.get("errors", ()))

    expected_statement: dict[str, Any] | None = None
    try:
        expected_statement = build_anchor_custody_statement(anchor)
    except (KeyError, TypeError, ValueError) as error:
        errors.append(str(error) or error.__class__.__name__)
    if expected_statement is None or dict(statement) != expected_statement:
        errors.append("WitnessAnchorCustodyStatementMismatch")
    predicate = statement.get("predicate")
    if not isinstance(predicate, Mapping) or any(
        predicate.get(name) is not False for name in _DENIED
    ):
        errors.append("WitnessAnchorCustodyAuthorityEscalation")

    allowed = tuple(allowed_custodian_ids)
    if (
        threshold != THRESHOLD
        or len(set(allowed)) != len(allowed)
        or threshold > len(allowed)
    ):
        errors.append("WitnessAnchorCustodyPolicyInvalid")
    if set(allowed) != set(CUSTODIAN_IDS):
        errors.append("WitnessAnchorCustodyRosterMismatch")
    if (
        not isinstance(custodian_fingerprints, Mapping)
        or set(custodian_fingerprints) != set(allowed)
        or any(
            not isinstance(value, str) or not value.startswith("SHA256:")
            for value in custodian_fingerprints.values()
        )
    ):
        errors.append("WitnessAnchorCustodyRosterFingerprintInvalid")
        fingerprints: Mapping[str, str] = {}
    else:
        fingerprints = custodian_fingerprints
    if len(set(fingerprints.values())) != len(allowed):
        errors.append("WitnessAnchorCustodyDuplicateKey")
    if (
        signatures is None
        or not isinstance(signatures, Sequence)
        or isinstance(signatures, (str, bytes))
    ):
        candidates: Sequence[Mapping[str, Any]] = ()
        errors.append("WitnessAnchorCustodySignaturesRequired")
    else:
        candidates = signatures

    valid_ids: list[str] = []
    seen: set[str] = set()
    signed_bytes = _canonical(statement)
    for item in candidates:
        try:
            if not isinstance(item, Mapping):
                raise ValueError("WitnessAnchorCustodySignatureInvalid")
            custodian_id = str(item["custodian_id"])
            signature = str(item["signature"])
            if custodian_id in seen:
                raise ValueError("WitnessAnchorCustodyDuplicateIdentity")
            seen.add(custodian_id)
            if custodian_id not in allowed:
                raise ValueError("WitnessAnchorCustodyIdentityUntrusted")
            if verifier is None or not verifier(custodian_id, signed_bytes, signature):
                raise ValueError("WitnessAnchorCustodySignatureInvalid")
            valid_ids.append(custodian_id)
        except (KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
            errors.append(str(error) or error.__class__.__name__)
    if len(valid_ids) < threshold:
        errors.append("WitnessAnchorCustodyThresholdNotMet")

    status = STATUS_REHEARSED if not errors else STATUS_HOLD
    result = {
        "schema": SCHEMA,
        "status": status,
        "anchor_sha256": anchor.get("anchor_sha256"),
        "statement_sha256": hashlib.sha256(signed_bytes).hexdigest(),
        "threshold": threshold,
        "valid_custodian_count": len(valid_ids),
        "valid_custodian_ids": sorted(valid_ids),
        "distinct_key_fingerprints_verified": len(set(fingerprints.values()))
        == threshold,
        "distinct_identities_verified": len(set(valid_ids)) >= threshold,
        "exact_anchor_recovery_verified": recovery.get("status")
        == STORAGE_RECOVERY_REHEARSED,
        "eligible_for_production_trust": False,
        "physical_operator_independence": "SIMULATED_NOT_PRODUCTION_PROVEN",
        "physical_power_loss_validated": False,
        "errors": list(dict.fromkeys(errors)),
        **{name: False for name in _DENIED},
    }
    result["result_sha256"] = hashlib.sha256(_canonical(result)).hexdigest()
    return result


__all__ = [
    "CUSTODIAN_IDS",
    "NAMESPACE",
    "SCHEMA",
    "STATUS_HOLD",
    "STATUS_REHEARSED",
    "THRESHOLD",
    "anchor_custody_statement_bytes",
    "build_anchor_custody_statement",
    "evaluate_threshold_anchor_custody",
]
