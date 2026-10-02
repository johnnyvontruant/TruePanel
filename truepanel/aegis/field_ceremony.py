"""Read-only coordinator for the single-operator AEGIS field ceremony.

The coordinator never creates a key, roster, kit, witness, or signature.  It
composes existing fail-closed verifiers and names the earliest JT-owned action
that is still required.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .operator_handoff import OPERATOR_KEY_ID
from .signing_tool import (
    audit_signing_kit,
    dual_audit_signing_kit,
    verify_returned_signature,
)
from .ssh_verifier import OpenSshSignatureVerifier
from .verifier_bootstrap import verify_verifier_release
from .verifier_confirmation import (
    load_verifier_confirmation_document,
    verify_verifier_confirmation_receipt,
)

FIELD_CEREMONY_SCHEMA = "truepanel.aegis-development-field-ceremony/v1"
_AUTHORITY = {
    "production_authority": False,
    "deployment_authority": False,
    "hardware_authority": False,
    "storage_write_authority": False,
    "automatic_promotion": False,
}


def _result(
    status: str,
    *,
    stages: list[dict[str, Any]],
    next_action: str,
    reason: str | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema": FIELD_CEREMONY_SCHEMA,
        "status": status,
        "completed_stages": stages,
        "next_action": next_action,
        "scope": "DEVELOPMENT_ONLY",
        "private_key_accepted": False,
        "signer_invoked": False,
        "runtime_writes": 0,
        **_AUTHORITY,
    }
    if reason is not None:
        value["reason"] = reason
    return value


def _hold(stages: list[dict[str, Any]], reason: str) -> dict[str, Any]:
    return _result("HOLD", stages=stages, next_action="CORRECT_INVALID_EVIDENCE", reason=reason)


def assess_field_ceremony(
    *,
    verifier_receipt_path: str | Path,
    verifier_source_path: str | Path,
    verifier_confirmation_receipt: Mapping[str, Any] | None = None,
    confirmation_observed_at: str | None = None,
    allowed_signers_path: str | Path | None = None,
    kit_directory: str | Path | None = None,
    independent_witness_path: str | Path | None = None,
    signature_path: str | Path | None = None,
    materials_path: str | Path | None = None,
    checkout_root: str | Path | None = None,
) -> dict[str, Any]:
    """Return the earliest unsatisfied ceremony gate without mutating state."""

    stages: list[dict[str, Any]] = []
    try:
        bootstrap = verify_verifier_release(
            receipt_path=verifier_receipt_path,
            source_path=verifier_source_path,
        )
    except ValueError as error:
        return _hold(stages, str(error))
    stages.append(
        {
            "stage": "verifier_content_pin",
            "status": bootstrap["status"],
            "source_sha256": bootstrap["source_sha256"],
        }
    )

    if verifier_confirmation_receipt is None and confirmation_observed_at is None:
        return _result(
            "ACTION_REQUIRED_INDEPENDENT_VERIFIER_CONFIRMATION",
            stages=stages,
            next_action="JT_CONFIRMS_VERIFIER_SHA256_THROUGH_INDEPENDENT_CHANNEL",
        )
    if verifier_confirmation_receipt is None or confirmation_observed_at is None:
        return _hold(stages, "IndependentVerifierConfirmationIncomplete")
    if verifier_confirmation_receipt.get("source_sha256") != bootstrap["source_sha256"]:
        return _hold(stages, "IndependentVerifierFingerprintMismatch")
    try:
        confirmation = verify_verifier_confirmation_receipt(
            receipt=verifier_confirmation_receipt,
            release=bootstrap,
            observed_at=confirmation_observed_at,
        )
    except ValueError as error:
        return _hold(stages, str(error))
    stages.append(
        {
            "stage": "independent_channel",
            "status": confirmation["status"],
            "source_sha256": confirmation["source_sha256"],
            "evidence_class": confirmation["evidence_class"],
            "confirmed_at": confirmation["confirmed_at"],
            "expires_at": confirmation["expires_at"],
        }
    )

    if allowed_signers_path is None:
        return _result(
            "ACTION_REQUIRED_PUBLIC_ROSTER",
            stages=stages,
            next_action="JT_PROVISIONS_DEVELOPMENT_PUBLIC_ROSTER",
        )
    try:
        roster = OpenSshSignatureVerifier(
            allowed_signers_path,
            expected_key_ids=(OPERATOR_KEY_ID,),
        ).inspect_roster()
    except (OSError, ValueError) as error:
        return _hold(stages, f"PublicRosterInvalid:{error}")
    stages.append(
        {
            "stage": "public_roster",
            "status": "PUBLIC_ROSTER_VALIDATED",
            "operator_key_id": OPERATOR_KEY_ID,
            "public_key_fingerprint": roster[OPERATOR_KEY_ID],
        }
    )

    if kit_directory is None:
        return _result(
            "ACTION_REQUIRED_SIGNING_KIT_EXPORT",
            stages=stages,
            next_action="EXPORT_PUBLIC_SIGNING_KIT_FROM_PINNED_CHECKOUT",
        )
    try:
        internal = audit_signing_kit(kit_directory)
    except ValueError as error:
        return _hold(stages, f"SigningKitInvalid:{error}")
    stages.append(
        {
            "stage": "internal_kit_audit",
            "status": internal["status"],
            "session_sha256": internal["session_sha256"],
        }
    )

    if independent_witness_path is None:
        return _result(
            "ACTION_REQUIRED_INDEPENDENT_KIT_AUDIT",
            stages=stages,
            next_action="RUN_PINNED_STANDALONE_AUDITOR",
        )
    try:
        dual = dual_audit_signing_kit(kit_directory, independent_witness_path)
    except ValueError as error:
        return _hold(stages, f"IndependentKitAuditInvalid:{error}")
    stages.append(
        {
            "stage": "dual_kit_audit",
            "status": dual["status"],
            "session_sha256": dual["session_sha256"],
            "auditors_agree": dual["auditors_agree"],
        }
    )

    if signature_path is None:
        return _result(
            "ACTION_REQUIRED_OFFLINE_SIGNATURE",
            stages=stages,
            next_action="JT_REVIEWS_AND_SIGNS_CANONICAL_SESSION_OFFLINE",
        )
    if materials_path is None or checkout_root is None:
        return _hold(stages, "ReturnedSignatureContextMissing")
    try:
        verified = verify_returned_signature(
            materials_path=materials_path,
            kit_directory=kit_directory,
            independent_witness_path=independent_witness_path,
            signature_path=signature_path,
            checkout_root=checkout_root,
            allowed_signers_path=allowed_signers_path,
        )
    except ValueError as error:
        return _hold(stages, f"ReturnedSignatureInvalid:{error}")
    if verified.get("status") != "ELIGIBLE_FOR_DEVELOPMENT_CANDIDATE_REVIEW":
        return _hold(stages, verified.get("reason", "ReturnedSignatureInvalid"))
    stages.append(
        {
            "stage": "returned_signature",
            "status": verified["status"],
            "dual_audit_bound": verified["dual_audit_bound"],
        }
    )
    return _result(
        "ELIGIBLE_FOR_DEVELOPMENT_CANDIDATE_REVIEW",
        stages=stages,
        next_action="INDEPENDENTLY_REVIEW_DEVELOPMENT_CANDIDATE",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Assess the read-only AEGIS development field ceremony"
    )
    parser.add_argument("--verifier-receipt", required=True, type=Path)
    parser.add_argument("--verifier-source", required=True, type=Path)
    parser.add_argument("--verifier-confirmation-receipt", type=Path)
    parser.add_argument("--confirmation-observed-at")
    parser.add_argument("--allowed-signers", type=Path)
    parser.add_argument("--kit", type=Path)
    parser.add_argument("--independent-witness", type=Path)
    parser.add_argument("--signature", type=Path)
    parser.add_argument("--materials", type=Path)
    parser.add_argument("--checkout", type=Path)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    values = build_parser().parse_args(arguments)
    confirmation = None
    if values.verifier_confirmation_receipt is not None:
        try:
            confirmation = load_verifier_confirmation_document(
                values.verifier_confirmation_receipt
            )
        except ValueError as error:
            print(json.dumps({"status": "HOLD", "reason": str(error)}, sort_keys=True))
            return 2
    result = assess_field_ceremony(
        verifier_receipt_path=values.verifier_receipt,
        verifier_source_path=values.verifier_source,
        verifier_confirmation_receipt=confirmation,
        confirmation_observed_at=values.confirmation_observed_at,
        allowed_signers_path=values.allowed_signers,
        kit_directory=values.kit,
        independent_witness_path=values.independent_witness,
        signature_path=values.signature,
        materials_path=values.materials,
        checkout_root=values.checkout,
    )
    print(json.dumps(result, sort_keys=True))
    return 2 if result["status"] == "HOLD" else 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "FIELD_CEREMONY_SCHEMA",
    "assess_field_ceremony",
]
