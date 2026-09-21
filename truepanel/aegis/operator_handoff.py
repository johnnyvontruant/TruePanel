"""Offline signing handoff for single-operator development review.

This module handles public material and deterministic statements only.  It has
no signer, private-key input, promotion consumer, or production authority.
"""

from __future__ import annotations

import json
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
    allowed_signers_path: str | Path,
) -> dict[str, Any]:
    """Build a portable, unsigned bundle after validating JT's public roster."""

    verifier = OpenSshSignatureVerifier(
        allowed_signers_path,
        namespace=DEVELOPMENT_NAMESPACE,
        expected_key_ids=(OPERATOR_KEY_ID,),
    )
    roster = verifier.inspect_roster()
    if (
        packet.get("schema") != DEVELOPMENT_PACKET_SCHEMA
        or unsigned_receipt.get("schema") != DEVELOPMENT_RECEIPT_SCHEMA
        or unsigned_receipt.get("signature") != ""
        or unsigned_receipt.get("packet_sha256") != semantic_sha256(packet)
        or policy.get("operator_id") != "jt"
        or policy.get("key_id") != OPERATOR_KEY_ID
        or policy.get("namespace") != DEVELOPMENT_NAMESPACE
    ):
        raise ValueError("DevelopmentHandoffInputsInvalid")
    statement = canonical_development_statement(unsigned_receipt)
    return {
        "schema": OPERATOR_HANDOFF_SCHEMA,
        "packet_sha256": semantic_sha256(packet),
        "receipt_sha256_without_signature": semantic_sha256(unsigned_receipt),
        "statement": statement.decode(),
        "statement_sha256": __import__("hashlib").sha256(statement).hexdigest(),
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
    now: float,
    consumed_receipts: Sequence[str] = (),
) -> dict[str, Any]:
    """Verify a returned detached signature; fail closed on handoff drift."""

    try:
        expected = build_operator_handoff(
            packet=packet,
            unsigned_receipt=unsigned_receipt,
            policy=policy,
            allowed_signers_path=allowed_signers_path,
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
