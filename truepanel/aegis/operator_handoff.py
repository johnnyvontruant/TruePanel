"""Offline signing handoff for single-operator development review.

This module handles public material and deterministic statements only.  It has
no signer, private-key input, promotion consumer, or production authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .acceptance import semantic_sha256
from .development_review import (
    DEVELOPMENT_NAMESPACE,
    DEVELOPMENT_PACKET_SCHEMA,
    DEVELOPMENT_RECEIPT_SCHEMA,
    development_statement,
    evaluate_development_receipt,
)
from .ssh_verifier import OpenSshSignatureVerifier

OPERATOR_HANDOFF_SCHEMA = "truepanel.aegis-development-operator-handoff/v1"
OPERATOR_KEY_ID = "jt-development-review"

_HANDOFF_FIELDS = {
    "schema",
    "packet_sha256",
    "receipt_sha256_without_signature",
    "statement",
    "statement_sha256",
    "namespace",
    "operator_id",
    "key_id",
    "public_key_fingerprint",
    "scope",
    "production_authority",
    "deployment_authority",
    "hardware_authority",
    "storage_write_authority",
    "automatic_promotion",
}


def canonical_development_statement(receipt: Mapping[str, Any]) -> bytes:
    """Serialize exactly the statement covered by the detached SSHSIG."""

    return json.dumps(
        development_statement(receipt),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def build_operator_handoff(
    *,
    packet: Mapping[str, Any],
    unsigned_receipt: Mapping[str, Any],
    policy: Mapping[str, Any],
    candidate: Mapping[str, Any],
    holodeck_evidence: Mapping[str, Any],
    coverage_matrix: Mapping[str, Any],
    reviewer_report: Mapping[str, Any],
    allowed_signers_path: str | Path,
    expected_source_commit: str,
    now: float,
) -> dict[str, Any]:
    """Issue a signing bundle only after every unsigned review check passes."""

    verifier = OpenSshSignatureVerifier(
        allowed_signers_path,
        namespace=DEVELOPMENT_NAMESPACE,
        expected_key_ids=(OPERATOR_KEY_ID,),
    )
    if (
        packet.get("schema") != DEVELOPMENT_PACKET_SCHEMA
        or unsigned_receipt.get("schema") != DEVELOPMENT_RECEIPT_SCHEMA
        or unsigned_receipt.get("signature") != ""
        or not isinstance(expected_source_commit, str)
        or re.fullmatch(r"[0-9a-f]{40}", expected_source_commit) is None
        or packet.get("source_commit") != expected_source_commit
        or policy.get("operator_id") != "jt"
        or policy.get("key_id") != OPERATOR_KEY_ID
        or policy.get("namespace") != DEVELOPMENT_NAMESPACE
    ):
        raise ValueError("DevelopmentHandoffInputsInvalid")
    try:
        # This is a preflight, not an approval. A deliberately false verifier
        # proves that all other checks pass before a signature is requested.
        preflight = evaluate_development_receipt(
            packet=packet,
            receipt=unsigned_receipt,
            policy=policy,
            candidate=candidate,
            holodeck_evidence=holodeck_evidence,
            coverage_matrix=coverage_matrix,
            reviewer_report=reviewer_report,
            verifier=lambda *_: False,
            now=now,
        )
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("DevelopmentHandoffPreflightInvalid") from error
    failures = [
        condition["reason"]
        for condition in preflight["conditions"]
        if not condition["passed"] and condition["condition"] != "operator_signature"
    ]
    if (
        preflight["status"] != "HOLD"
        or not any(
            condition["condition"] == "operator_signature" and not condition["passed"]
            for condition in preflight["conditions"]
        )
    ):
        raise ValueError("DevelopmentHandoffPreflightInvariantFailed")
    if failures:
        raise ValueError(f"DevelopmentHandoffPreflightFailed:{failures[0]}")
    roster = verifier.inspect_roster()
    statement = canonical_development_statement(unsigned_receipt)
    return {
        "schema": OPERATOR_HANDOFF_SCHEMA,
        "packet_sha256": semantic_sha256(packet),
        "receipt_sha256_without_signature": semantic_sha256(unsigned_receipt),
        "statement": statement.decode(),
        "statement_sha256": hashlib.sha256(statement).hexdigest(),
        "namespace": DEVELOPMENT_NAMESPACE,
        "operator_id": "jt",
        "key_id": OPERATOR_KEY_ID,
        "public_key_fingerprint": roster[OPERATOR_KEY_ID],
        "scope": "DEVELOPMENT_ONLY",
        "production_authority": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "storage_write_authority": False,
        "automatic_promotion": False,
    }


def verify_operator_handoff(
    *,
    handoff: Mapping[str, Any],
    packet: Mapping[str, Any],
    unsigned_receipt: Mapping[str, Any],
    signature: str,
    policy: Mapping[str, Any],
    candidate: Mapping[str, Any],
    holodeck_evidence: Mapping[str, Any],
    coverage_matrix: Mapping[str, Any],
    reviewer_report: Mapping[str, Any],
    allowed_signers_path: str | Path,
    expected_source_commit: str,
    now: float,
    consumed_receipts: Sequence[str] = (),
) -> dict[str, Any]:
    """Verify a returned detached signature; fail closed on handoff drift."""

    try:
        expected = build_operator_handoff(
            packet=packet,
            unsigned_receipt=unsigned_receipt,
            policy=policy,
            candidate=candidate,
            holodeck_evidence=holodeck_evidence,
            coverage_matrix=coverage_matrix,
            reviewer_report=reviewer_report,
            allowed_signers_path=allowed_signers_path,
            expected_source_commit=expected_source_commit,
            now=now,
        )
    except (OSError, ValueError):
        expected = None
    exact = set(handoff) == _HANDOFF_FIELDS and handoff == expected
    if not exact:
        return {
            "status": "HOLD",
            "reason": "OperatorHandoffMismatch",
            "production_authority": False,
            "deployment_authority": False,
            "hardware_authority": False,
            "storage_write_authority": False,
            "automatic_promotion": False,
            "receipt_consumed": False,
            "runtime_writes": 0,
        }
    signed_receipt = dict(unsigned_receipt)
    signed_receipt["signature"] = signature
    verifier = OpenSshSignatureVerifier(
        allowed_signers_path,
        namespace=DEVELOPMENT_NAMESPACE,
        expected_key_ids=(OPERATOR_KEY_ID,),
        expected_fingerprint=handoff["public_key_fingerprint"],
    )
    return evaluate_development_receipt(
        packet=packet,
        receipt=signed_receipt,
        policy=policy,
        candidate=candidate,
        holodeck_evidence=holodeck_evidence,
        coverage_matrix=coverage_matrix,
        reviewer_report=reviewer_report,
        verifier=verifier,
        now=now,
        consumed_receipts=consumed_receipts,
    )


__all__ = [
    "OPERATOR_HANDOFF_SCHEMA",
    "OPERATOR_KEY_ID",
    "build_operator_handoff",
    "canonical_development_statement",
    "verify_operator_handoff",
]
