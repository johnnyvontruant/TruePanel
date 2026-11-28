"""Quorum-preserving recovery policy for compromised anchor custodians."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final

from .transparency_witness_anchor_rotation import (
    NEXT_CUSTODIAN_IDS as CURRENT_CUSTODIAN_IDS,
)

SCHEMA: Final = "truepanel.aegis-witness-custodian-compromise-recovery/v1"
STATEMENT_TYPE: Final = "https://in-toto.io/Statement/v1"
PREDICATE_TYPE: Final = (
    "https://truepanel.dev/attestations/aegis-witness-custodian-compromise-recovery/v1"
)
NAMESPACE: Final = "truepanel-aegis-witness-custodian-compromise-recovery-v1@truepanel"
THRESHOLD: Final = 2
EXPANDED_CUSTODIAN_IDS: Final = (
    *CURRENT_CUSTODIAN_IDS,
    "aegis-anchor-custodian-delta@holodeck.invalid",
)
RECOVERED_CUSTODIAN_IDS: Final = (
    CURRENT_CUSTODIAN_IDS[0],
    EXPANDED_CUSTODIAN_IDS[2],
    "aegis-anchor-custodian-echo@holodeck.invalid",
)
REVOKED_CUSTODIAN_ID: Final = CURRENT_CUSTODIAN_IDS[1]
STATUS_REHEARSED: Final = "CUSTODIAN_COMPROMISE_RECOVERY_REHEARSED"
STATUS_HOLD: Final = "CUSTODIAN_COMPROMISE_RECOVERY_HOLD"
_ROOT_SCHEMA: Final = "truepanel.aegis-witness-anchor-custodian-root/v1"
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


def build_compromise_recovery_statement(
    current_root: Mapping[str, Any],
    expanded_root: Mapping[str, Any],
    recovered_root: Mapping[str, Any],
    *,
    predecessor_evidence_sha256: str,
    revoked_custodian_id: str = REVOKED_CUSTODIAN_ID,
) -> dict[str, Any]:
    """Bind proactive quorum expansion and subsequent key revocation."""
    if len(predecessor_evidence_sha256) != 64:
        raise ValueError("WitnessCustodianRecoveryPredecessorEvidenceInvalid")
    fingerprints = expanded_root.get("custodian_fingerprints")
    if (
        not isinstance(fingerprints, Mapping)
        or revoked_custodian_id not in fingerprints
    ):
        raise ValueError("WitnessCustodianRecoveryRevokedIdentityMissing")
    return {
        "_type": STATEMENT_TYPE,
        "subject": [
            {
                "name": "truepanel-witness-anchor-recovered-custodian-root.json",
                "digest": {"sha256": recovered_root["root_sha256"]},
            }
        ],
        "predicateType": PREDICATE_TYPE,
        "predicate": {
            "schema": SCHEMA,
            "namespace": NAMESPACE,
            "predecessor_evidence_sha256": predecessor_evidence_sha256,
            "current_root_sha256": current_root["root_sha256"],
            "expanded_root_sha256": expanded_root["root_sha256"],
            "recovered_root_sha256": recovered_root["root_sha256"],
            "versions": [
                current_root["version"],
                expanded_root["version"],
                recovered_root["version"],
            ],
            "threshold": THRESHOLD,
            "revoked_custodian_id": revoked_custodian_id,
            "revoked_key_fingerprint": fingerprints[revoked_custodian_id],
            "revocation_effective_version": recovered_root["version"],
            "recovery_order": "EXPAND_QUORUM_THEN_REVOKE_AND_REPLACE",
            "compromised_private_key_used_after_revocation": False,
            "physical_operator_independence": "SIMULATED_NOT_PRODUCTION_PROVEN",
            **{name: False for name in _DENIED},
        },
    }


def compromise_recovery_statement_bytes(statement: Mapping[str, Any]) -> bytes:
    return _canonical(statement)


def quorum_expansion_statement_bytes(
    current_root: Mapping[str, Any],
    expanded_root: Mapping[str, Any],
    predecessor_evidence_sha256: str,
) -> bytes:
    """Return the exact first-stage expansion statement signed by both rosters."""
    return _canonical(
        {
            "purpose": "QUORUM_EXPANSION",
            "current_root_sha256": current_root.get("root_sha256"),
            "next_root_sha256": expanded_root.get("root_sha256"),
            "predecessor_evidence_sha256": predecessor_evidence_sha256,
        }
    )


def _root_errors(
    root: Mapping[str, Any], expected_ids: Sequence[str], label: str
) -> list[str]:
    errors: list[str] = []
    payload = {key: value for key, value in root.items() if key != "root_sha256"}
    fingerprints = root.get("custodian_fingerprints")
    valid_fingerprints = isinstance(fingerprints, Mapping) and (
        set(fingerprints) == set(expected_ids)
        and len(fingerprints) == len(set(expected_ids))
        and len(set(fingerprints.values())) == len(fingerprints)
        and all(
            isinstance(value, str) and value.startswith("SHA256:")
            for value in fingerprints.values()
        )
    )
    if (
        root.get("schema") != _ROOT_SCHEMA
        or root.get("root_sha256") != _digest(payload)
        or root.get("threshold") != THRESHOLD
        or not valid_fingerprints
        or any(root.get(name) is not False for name in _DENIED)
    ):
        errors.append(f"WitnessCustodianRecovery{label}RootInvalid")
    return errors


def _verify_threshold(
    *,
    signatures: Sequence[Mapping[str, Any]] | None,
    allowed_ids: Sequence[str],
    excluded_ids: Sequence[str],
    statement_bytes: bytes,
    verifier: Callable[[str, bytes, str], bool] | None,
    label: str,
) -> tuple[list[str], list[str]]:
    valid: list[str] = []
    errors: list[str] = []
    if (
        signatures is None
        or not isinstance(signatures, Sequence)
        or isinstance(signatures, (str, bytes))
    ):
        return valid, [f"WitnessCustodianRecovery{label}SignaturesRequired"]
    allowed = set(allowed_ids)
    excluded = set(excluded_ids)
    seen: set[str] = set()
    for item in signatures:
        try:
            if not isinstance(item, Mapping):
                raise ValueError(f"WitnessCustodianRecovery{label}SignatureInvalid")
            identity = str(item["custodian_id"])
            signature = str(item["signature"])
            if identity in seen:
                raise ValueError(f"WitnessCustodianRecovery{label}DuplicateIdentity")
            seen.add(identity)
            if identity in excluded:
                raise ValueError(f"WitnessCustodianRecovery{label}RevokedIdentityUsed")
            if identity not in allowed:
                raise ValueError(f"WitnessCustodianRecovery{label}IdentityUntrusted")
            if verifier is None or not verifier(identity, statement_bytes, signature):
                raise ValueError(f"WitnessCustodianRecovery{label}SignatureInvalid")
            valid.append(identity)
        except (KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
            errors.append(str(error) or error.__class__.__name__)
    if len(set(valid)) < THRESHOLD:
        errors.append(f"WitnessCustodianRecovery{label}ThresholdNotMet")
    return valid, errors


def evaluate_custodian_compromise_recovery(
    current_root: Mapping[str, Any],
    expanded_root: Mapping[str, Any],
    recovered_root: Mapping[str, Any],
    predecessor_evidence_sha256: str,
    statement: Mapping[str, Any],
    current_signatures: Sequence[Mapping[str, Any]] | None,
    expanded_signatures: Sequence[Mapping[str, Any]] | None,
    recovery_current_signatures: Sequence[Mapping[str, Any]] | None,
    recovered_signatures: Sequence[Mapping[str, Any]] | None,
    current_verifier: Callable[[str, bytes, str], bool] | None,
    expanded_verifier: Callable[[str, bytes, str], bool] | None,
    recovered_verifier: Callable[[str, bytes, str], bool] | None,
) -> dict[str, Any]:
    """Rehearse 2-of-2 -> 2-of-3 expansion before compromise recovery."""
    errors = _root_errors(current_root, CURRENT_CUSTODIAN_IDS, "Current")
    errors.extend(_root_errors(expanded_root, EXPANDED_CUSTODIAN_IDS, "Expanded"))
    errors.extend(_root_errors(recovered_root, RECOVERED_CUSTODIAN_IDS, "Recovered"))
    versions = [
        current_root.get("version"),
        expanded_root.get("version"),
        recovered_root.get("version"),
    ]
    if (
        any(not isinstance(value, int) or isinstance(value, bool) for value in versions)
        or versions[1] != versions[0] + 1
        or versions[2] != versions[1] + 1
    ):
        errors.append("WitnessCustodianRecoveryVersionsNotConsecutive")
    if expanded_root.get("predecessor_root_sha256") != current_root.get(
        "root_sha256"
    ) or recovered_root.get("predecessor_root_sha256") != expanded_root.get(
        "root_sha256"
    ):
        errors.append("WitnessCustodianRecoveryPredecessorMismatch")
    for field in ("anchor_statement_sha256", "custody_evidence_sha256"):
        if (
            len(
                {
                    current_root.get(field),
                    expanded_root.get(field),
                    recovered_root.get(field),
                }
            )
            != 1
        ):
            errors.append("WitnessCustodianRecoveryEvidenceContinuityMismatch")
    current_fingerprints = current_root.get("custodian_fingerprints", {})
    expanded_fingerprints = expanded_root.get("custodian_fingerprints", {})
    recovered_fingerprints = recovered_root.get("custodian_fingerprints", {})
    if not isinstance(current_fingerprints, Mapping):
        current_fingerprints = {}
    if not isinstance(expanded_fingerprints, Mapping):
        expanded_fingerprints = {}
    if not isinstance(recovered_fingerprints, Mapping):
        recovered_fingerprints = {}
    if not all(
        expanded_fingerprints.get(identity) == fingerprint
        for identity, fingerprint in current_fingerprints.items()
    ):
        errors.append("WitnessCustodianRecoveryExpansionChangedExistingKey")
    if REVOKED_CUSTODIAN_ID in recovered_fingerprints or (
        expanded_fingerprints.get(REVOKED_CUSTODIAN_ID)
        in set(recovered_fingerprints.values())
    ):
        errors.append("WitnessCustodianRecoveryRevokedKeyStillTrusted")
    retained = set(EXPANDED_CUSTODIAN_IDS) - {REVOKED_CUSTODIAN_ID}
    if len(retained & set(RECOVERED_CUSTODIAN_IDS)) < THRESHOLD:
        errors.append("WitnessCustodianRecoveryUnaffectedQuorumLost")
    try:
        expected_statement = build_compromise_recovery_statement(
            current_root,
            expanded_root,
            recovered_root,
            predecessor_evidence_sha256=predecessor_evidence_sha256,
        )
    except (KeyError, TypeError, ValueError) as error:
        expected_statement = None
        errors.append(str(error) or error.__class__.__name__)
    if expected_statement is None or dict(statement) != expected_statement:
        errors.append("WitnessCustodianRecoveryStatementMismatch")
    predicate = statement.get("predicate")
    if not isinstance(predicate, Mapping) or any(
        predicate.get(name) is not False for name in _DENIED
    ):
        errors.append("WitnessCustodianRecoveryAuthorityEscalation")

    expansion_bytes = quorum_expansion_statement_bytes(
        current_root, expanded_root, predecessor_evidence_sha256
    )
    recovery_bytes = compromise_recovery_statement_bytes(statement)
    current_valid, current_errors = _verify_threshold(
        signatures=current_signatures,
        allowed_ids=CURRENT_CUSTODIAN_IDS,
        excluded_ids=(),
        statement_bytes=expansion_bytes,
        verifier=current_verifier,
        label="ExpansionCurrent",
    )
    expanded_valid, expanded_errors = _verify_threshold(
        signatures=expanded_signatures,
        allowed_ids=EXPANDED_CUSTODIAN_IDS,
        excluded_ids=(),
        statement_bytes=expansion_bytes,
        verifier=expanded_verifier,
        label="ExpansionNext",
    )
    recovery_current_valid, recovery_current_errors = _verify_threshold(
        signatures=recovery_current_signatures,
        allowed_ids=EXPANDED_CUSTODIAN_IDS,
        excluded_ids=(REVOKED_CUSTODIAN_ID,),
        statement_bytes=recovery_bytes,
        verifier=expanded_verifier,
        label="RecoveryCurrent",
    )
    recovered_valid, recovered_errors = _verify_threshold(
        signatures=recovered_signatures,
        allowed_ids=RECOVERED_CUSTODIAN_IDS,
        excluded_ids=(REVOKED_CUSTODIAN_ID,),
        statement_bytes=recovery_bytes,
        verifier=recovered_verifier,
        label="RecoveryNext",
    )
    errors.extend(current_errors + expanded_errors)
    errors.extend(recovery_current_errors + recovered_errors)
    result = {
        "schema": SCHEMA,
        "status": STATUS_REHEARSED if not errors else STATUS_HOLD,
        "versions": versions,
        "current_roster_size": len(CURRENT_CUSTODIAN_IDS),
        "expanded_roster_size": len(EXPANDED_CUSTODIAN_IDS),
        "recovered_roster_size": len(RECOVERED_CUSTODIAN_IDS),
        "threshold": THRESHOLD,
        "current_failure_tolerance": len(CURRENT_CUSTODIAN_IDS) - THRESHOLD,
        "expanded_failure_tolerance": len(EXPANDED_CUSTODIAN_IDS) - THRESHOLD,
        "recovered_failure_tolerance": len(RECOVERED_CUSTODIAN_IDS) - THRESHOLD,
        "revoked_custodian_id": REVOKED_CUSTODIAN_ID,
        "current_valid_custodian_ids": sorted(current_valid),
        "expanded_valid_custodian_ids": sorted(expanded_valid),
        "recovery_current_valid_custodian_ids": sorted(recovery_current_valid),
        "recovered_valid_custodian_ids": sorted(recovered_valid),
        "revoked_key_used_after_revocation": REVOKED_CUSTODIAN_ID
        in set(recovery_current_valid + recovered_valid),
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
    "EXPANDED_CUSTODIAN_IDS",
    "NAMESPACE",
    "RECOVERED_CUSTODIAN_IDS",
    "REVOKED_CUSTODIAN_ID",
    "SCHEMA",
    "STATUS_HOLD",
    "STATUS_REHEARSED",
    "THRESHOLD",
    "build_compromise_recovery_statement",
    "compromise_recovery_statement_bytes",
    "evaluate_custodian_compromise_recovery",
    "quorum_expansion_statement_bytes",
]
