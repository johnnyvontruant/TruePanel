"""Content-bound offline signing session for development-only AEGIS review."""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .acceptance import semantic_sha256
from .development_review import evaluate_development_receipt
from .operator_handoff import (
    OPERATOR_KEY_ID,
    build_operator_handoff,
    canonical_development_statement,
)
from .ssh_verifier import OpenSshSignatureVerifier

SIGNING_SESSION_SCHEMA = "truepanel.aegis-development-signing-session/v1"
CHECKOUT_WITNESS_SCHEMA = "truepanel.aegis-clean-checkout-witness/v1"
CLOCK_WITNESS_SCHEMA = "truepanel.aegis-operator-clock-witness/v1"
SIGNING_SESSION_NAMESPACE = "truepanel-aegis-development-signing-session-v1@truepanel"

_SESSION_FIELDS = {
    "schema", "handoff", "checkout_witness", "clock_witness", "receipt_sha256",
    "scope", "production_authority", "deployment_authority", "hardware_authority",
    "storage_write_authority", "automatic_promotion",
}
_CHECKOUT_FIELDS = {
    "schema", "commit", "tree", "clean", "submodules_clean", "object_replacement_disabled",
}
_CLOCK_FIELDS = {
    "schema", "source", "operator_id", "observed_at", "unix_seconds", "confirmed",
}


def _git(root: Path, *arguments: str) -> str:
    environment = dict(os.environ)
    environment["GIT_NO_REPLACE_OBJECTS"] = "1"
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
        env=environment,
    )
    return completed.stdout


def witness_clean_checkout(root: str | Path, *, expected_commit: str) -> dict[str, Any]:
    """Read Git metadata without changing the checkout and reject any drift."""

    path = Path(root)
    if path.is_symlink() or not path.is_absolute():
        raise ValueError("CheckoutPathUnsafe")
    try:
        resolved = path.resolve(strict=True)
        top = Path(_git(resolved, "rev-parse", "--show-toplevel").strip()).resolve(strict=True)
        commit = _git(resolved, "rev-parse", "HEAD^{commit}").strip()
        tree = _git(resolved, "rev-parse", "HEAD^{tree}").strip()
        dirty = _git(resolved, "status", "--porcelain=v1", "--untracked-files=all")
        submodules = _git(resolved, "submodule", "status", "--recursive")
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError("CheckoutInspectionFailed") from error
    if (
        top != resolved
        or re.fullmatch(r"[0-9a-f]{40}", expected_commit) is None
        or commit != expected_commit
        or re.fullmatch(r"[0-9a-f]{40}", tree) is None
        or dirty
        or any(line and not line.startswith(" ") for line in submodules.splitlines())
    ):
        raise ValueError("CheckoutWitnessHold")
    return {
        "schema": CHECKOUT_WITNESS_SCHEMA,
        "commit": commit,
        "tree": tree,
        "clean": True,
        "submodules_clean": True,
        "object_replacement_disabled": True,
    }


def build_clock_witness(*, observed_at: str, unix_seconds: float, confirmed_by: str) -> dict[str, Any]:
    """Record JT's explicit UTC observation; this does not claim network time."""

    if not isinstance(observed_at, str):
        raise ValueError("ClockWitnessInvalid")
    try:
        parsed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone required")
        timestamp = parsed.astimezone(UTC).timestamp()
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("ClockWitnessInvalid") from error
    if (
        confirmed_by != "jt"
        or isinstance(unix_seconds, bool)
        or not isinstance(unix_seconds, (int, float))
        or not math.isfinite(float(unix_seconds))
        or not observed_at.endswith("Z")
        or abs(timestamp - float(unix_seconds)) > 1.0
    ):
        raise ValueError("ClockWitnessInvalid")
    return {
        "schema": CLOCK_WITNESS_SCHEMA,
        "source": "OPERATOR_CONFIRMED_UTC",
        "operator_id": "jt",
        "observed_at": observed_at,
        "unix_seconds": float(unix_seconds),
        "confirmed": True,
    }


def build_signing_session(
    *, checkout_root: str | Path, clock_witness: Mapping[str, Any], packet: Mapping[str, Any],
    unsigned_receipt: Mapping[str, Any], policy: Mapping[str, Any], candidate: Mapping[str, Any],
    holodeck_evidence: Mapping[str, Any], coverage_matrix: Mapping[str, Any],
    reviewer_report: Mapping[str, Any], allowed_signers_path: str | Path,
) -> dict[str, Any]:
    """Bind source, time, handoff, and receipt into one offline statement."""

    if set(clock_witness) != _CLOCK_FIELDS or clock_witness.get("confirmed") is not True:
        raise ValueError("ClockWitnessInvalid")
    expected_clock = build_clock_witness(
        observed_at=clock_witness["observed_at"],
        unix_seconds=clock_witness["unix_seconds"],
        confirmed_by=clock_witness["operator_id"],
    )
    if dict(clock_witness) != expected_clock:
        raise ValueError("ClockWitnessInvalid")
    now = float(expected_clock["unix_seconds"])
    expected_commit = str(packet.get("source_commit", ""))
    checkout = witness_clean_checkout(checkout_root, expected_commit=expected_commit)
    handoff = build_operator_handoff(
        packet=packet,
        unsigned_receipt=unsigned_receipt,
        policy=policy,
        candidate=candidate,
        holodeck_evidence=holodeck_evidence,
        coverage_matrix=coverage_matrix,
        reviewer_report=reviewer_report,
        allowed_signers_path=allowed_signers_path,
        expected_source_commit=expected_commit,
        now=now,
    )
    return {
        "schema": SIGNING_SESSION_SCHEMA,
        "handoff": handoff,
        "checkout_witness": checkout,
        "clock_witness": expected_clock,
        "receipt_sha256": semantic_sha256(unsigned_receipt),
        "scope": "DEVELOPMENT_ONLY",
        "production_authority": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "storage_write_authority": False,
        "automatic_promotion": False,
    }


def canonical_signing_session_statement(session: Mapping[str, Any]) -> bytes:
    return json.dumps(session, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def verify_signing_session(
    *, session: Mapping[str, Any], signature: str, checkout_root: str | Path,
    clock_witness: Mapping[str, Any], packet: Mapping[str, Any], unsigned_receipt: Mapping[str, Any],
    policy: Mapping[str, Any], candidate: Mapping[str, Any], holodeck_evidence: Mapping[str, Any],
    coverage_matrix: Mapping[str, Any], reviewer_report: Mapping[str, Any],
    allowed_signers_path: str | Path, consumed_receipts: Sequence[str] = (),
) -> dict[str, Any]:
    """Rebuild and verify the whole session before evaluating development eligibility."""

    try:
        expected = build_signing_session(
            checkout_root=checkout_root, clock_witness=clock_witness, packet=packet,
            unsigned_receipt=unsigned_receipt, policy=policy, candidate=candidate,
            holodeck_evidence=holodeck_evidence, coverage_matrix=coverage_matrix,
            reviewer_report=reviewer_report, allowed_signers_path=allowed_signers_path,
        )
    except (OSError, TypeError, ValueError):
        expected = None
    if set(session) != _SESSION_FIELDS or session != expected or set(session.get("checkout_witness", {})) != _CHECKOUT_FIELDS:
        return _hold("SigningSessionMismatch")
    verifier = OpenSshSignatureVerifier(
        allowed_signers_path,
        namespace=SIGNING_SESSION_NAMESPACE,
        expected_key_ids=(OPERATOR_KEY_ID,),
        expected_fingerprint=session["handoff"]["public_key_fingerprint"],
    )
    session_valid = verifier(OPERATOR_KEY_ID, canonical_signing_session_statement(session), signature)
    receipt_statement = canonical_development_statement(unsigned_receipt)
    signed_receipt = dict(unsigned_receipt)
    signed_receipt["signature"] = signature

    def receipt_verifier(key_id: str, statement: bytes, candidate_signature: str) -> bool:
        return (
            session_valid
            and key_id == OPERATOR_KEY_ID
            and statement == receipt_statement
            and candidate_signature == signature
        )

    return evaluate_development_receipt(
        packet=packet, receipt=signed_receipt, policy=policy, candidate=candidate,
        holodeck_evidence=holodeck_evidence, coverage_matrix=coverage_matrix,
        reviewer_report=reviewer_report, verifier=receipt_verifier,
        now=float(clock_witness["unix_seconds"]), consumed_receipts=consumed_receipts,
    )


def _hold(reason: str) -> dict[str, Any]:
    return {
        "status": "HOLD", "reason": reason, "production_authority": False,
        "deployment_authority": False, "hardware_authority": False,
        "storage_write_authority": False, "automatic_promotion": False,
        "receipt_consumed": False, "runtime_writes": 0,
    }


__all__ = [
    "SIGNING_SESSION_NAMESPACE", "SIGNING_SESSION_SCHEMA", "build_clock_witness",
    "build_signing_session", "canonical_signing_session_statement", "verify_signing_session",
    "witness_clean_checkout",
]
