"""Content-bound operator attestation for verifier fingerprint comparison.

This module records that JT compared an independently obtained public digest.
It does not prove channel independence, authenticate JT cryptographically, or
grant signing, production, deployment, storage, or hardware authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .verifier_bootstrap import RELEASE_ID, verify_verifier_release

CHALLENGE_SCHEMA = "truepanel.aegis-verifier-confirmation-challenge/v1"
RECEIPT_SCHEMA = "truepanel.aegis-verifier-confirmation-receipt/v1"
CONFIRMATION_STATUS = "OPERATOR_ATTESTED_INDEPENDENT_CHANNEL"
EVIDENCE_CLASS = "OPERATOR_ATTESTATION_NOT_CRYPTOGRAPHIC_PROOF"
OPERATOR_STATEMENT = (
    "JT compared the complete verifier SHA-256 obtained through the named "
    "operator-controlled channel and observed an exact match."
)
VALIDITY = timedelta(minutes=30)
MAX_BYTES = 1024 * 1024

_CHANNELS = (
    "OPERATOR_SECURE_NOTE",
    "PRINTED_COPY",
    "SEPARATE_OPERATOR_DEVICE",
    "VERBAL_READBACK",
)
_AUTHORITY = {
    "production_authority": False,
    "deployment_authority": False,
    "hardware_authority": False,
    "storage_write_authority": False,
    "automatic_promotion": False,
}
_RELEASE_FIELDS = {
    "schema",
    "status",
    "release_id",
    "source_commit",
    "source_sha256",
    "source_git_blob_sha1",
    "independent_channel_verified",
    "next_gate",
    "scope",
    *_AUTHORITY,
}
_CHALLENGE_FIELDS = {
    "schema",
    "status",
    "release_id",
    "source_commit",
    "source_sha256",
    "fingerprint_blocks",
    "allowed_channels",
    "operator_id",
    "operator_statement",
    "evidence_class",
    "scope",
    *_AUTHORITY,
}
_RECEIPT_FIELDS = {
    "schema",
    "status",
    "release_id",
    "source_commit",
    "source_sha256",
    "challenge_sha256",
    "channel",
    "confirmed_at",
    "expires_at",
    "operator_id",
    "operator_statement",
    "evidence_class",
    "independent_channel_claimed",
    "independent_channel_cryptographically_verified",
    "private_key_accepted",
    "signer_invoked",
    "scope",
    *_AUTHORITY,
}


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError("VerifierConfirmationDuplicateJsonKey")
        document[key] = value
    return document


def load_verifier_confirmation_document(path: str | Path) -> dict[str, Any]:
    """Load one bounded regular JSON document without following symlinks."""

    value = Path(path)
    if not value.is_absolute() or value.is_symlink() or not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("VerifierConfirmationUnsafePath")
    try:
        if value.resolve(strict=True) != value:
            raise ValueError("VerifierConfirmationUnsafePath")
        descriptor = os.open(value, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            before = os.fstat(descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_size <= 0
                or before.st_size > MAX_BYTES
            ):
                raise ValueError("VerifierConfirmationInvalidFile")
            content = b""
            while len(content) <= MAX_BYTES:
                chunk = os.read(descriptor, min(65536, MAX_BYTES + 1 - len(content)))
                if not chunk:
                    break
                content += chunk
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise ValueError("VerifierConfirmationUnavailableFile") from error

    def identity(item: os.stat_result) -> tuple[int, ...]:
        return (
            item.st_dev,
            item.st_ino,
            item.st_mode,
            item.st_size,
            item.st_mtime_ns,
            item.st_ctime_ns,
        )

    if len(content) > MAX_BYTES or identity(before) != identity(after):
        raise ValueError("VerifierConfirmationChangingFile")
    try:
        document = json.loads(content, object_pairs_hook=_no_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("VerifierConfirmationInvalidJson") from error
    if not isinstance(document, dict):
        raise ValueError("VerifierConfirmationInvalidJson")
    if content != _canonical(document) + b"\n":
        raise ValueError("VerifierConfirmationDocumentNotCanonical")
    return document


def _semantic_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("VerifierConfirmationTimestampInvalid")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as error:
        raise ValueError("VerifierConfirmationTimestampInvalid") from error
    return parsed


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _valid_release(release: Mapping[str, Any]) -> bool:
    value = dict(release)
    return (
        set(value) == _RELEASE_FIELDS
        and value.get("status") == "VERIFIER_CONTENT_PIN_VERIFIED"
        and value.get("release_id") == RELEASE_ID
        and value.get("independent_channel_verified") is False
        and value.get("scope") == "DEVELOPMENT_ONLY"
        and isinstance(value.get("source_commit"), str)
        and len(value["source_commit"]) == 40
        and isinstance(value.get("source_sha256"), str)
        and len(value["source_sha256"]) == 64
        and not any(
            value.get(field) is not expected for field, expected in _AUTHORITY.items()
        )
    )


def build_verifier_confirmation_challenge(
    release: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the exact public comparison challenge from a verified release."""

    if not _valid_release(release):
        raise ValueError("VerifierConfirmationReleaseInvalid")
    digest = str(release["source_sha256"])
    return {
        "schema": CHALLENGE_SCHEMA,
        "status": "READY_FOR_OUT_OF_BAND_COMPARISON",
        "release_id": RELEASE_ID,
        "source_commit": release["source_commit"],
        "source_sha256": digest,
        "fingerprint_blocks": [digest[index : index + 8] for index in range(0, 64, 8)],
        "allowed_channels": list(_CHANNELS),
        "operator_id": "jt",
        "operator_statement": OPERATOR_STATEMENT,
        "evidence_class": EVIDENCE_CLASS,
        "scope": "DEVELOPMENT_ONLY",
        **_AUTHORITY,
    }


def verifier_confirmation_challenge_sha256(challenge: Mapping[str, Any]) -> str:
    return _semantic_sha256(challenge)


def create_verifier_confirmation_receipt(
    *,
    challenge: Mapping[str, Any],
    independently_observed_sha256: str,
    channel: str,
    confirmed_at: str,
) -> dict[str, Any]:
    """Record an exact human comparison without claiming cryptographic proof."""

    value = dict(challenge)
    if (
        set(value) != _CHALLENGE_FIELDS
        or value.get("schema") != CHALLENGE_SCHEMA
        or value.get("status") != "READY_FOR_OUT_OF_BAND_COMPARISON"
        or value.get("release_id") != RELEASE_ID
        or value.get("operator_id") != "jt"
        or value.get("operator_statement") != OPERATOR_STATEMENT
        or value.get("evidence_class") != EVIDENCE_CLASS
        or value.get("allowed_channels") != list(_CHANNELS)
        or value.get("scope") != "DEVELOPMENT_ONLY"
        or any(value.get(field) is not expected for field, expected in _AUTHORITY.items())
    ):
        raise ValueError("VerifierConfirmationChallengeInvalid")
    if independently_observed_sha256 != value.get("source_sha256"):
        raise ValueError("IndependentVerifierFingerprintMismatch")
    if channel not in _CHANNELS:
        raise ValueError("VerifierConfirmationChannelInvalid")
    confirmed = _timestamp(confirmed_at)
    return {
        "schema": RECEIPT_SCHEMA,
        "status": CONFIRMATION_STATUS,
        "release_id": RELEASE_ID,
        "source_commit": value["source_commit"],
        "source_sha256": value["source_sha256"],
        "challenge_sha256": verifier_confirmation_challenge_sha256(value),
        "channel": channel,
        "confirmed_at": _format_timestamp(confirmed),
        "expires_at": _format_timestamp(confirmed + VALIDITY),
        "operator_id": "jt",
        "operator_statement": OPERATOR_STATEMENT,
        "evidence_class": EVIDENCE_CLASS,
        "independent_channel_claimed": True,
        "independent_channel_cryptographically_verified": False,
        "private_key_accepted": False,
        "signer_invoked": False,
        "scope": "DEVELOPMENT_ONLY",
        **_AUTHORITY,
    }


def verify_verifier_confirmation_receipt(
    *,
    receipt: Mapping[str, Any],
    release: Mapping[str, Any],
    observed_at: str,
) -> dict[str, Any]:
    """Reconstruct and validate one short-lived operator attestation."""

    challenge = build_verifier_confirmation_challenge(release)
    value = dict(receipt)
    if (
        set(value) != _RECEIPT_FIELDS
        or value.get("schema") != RECEIPT_SCHEMA
        or value.get("status") != CONFIRMATION_STATUS
        or value.get("release_id") != RELEASE_ID
        or value.get("source_commit") != release.get("source_commit")
        or value.get("source_sha256") != release.get("source_sha256")
        or value.get("challenge_sha256")
        != verifier_confirmation_challenge_sha256(challenge)
        or value.get("channel") not in _CHANNELS
        or value.get("operator_id") != "jt"
        or value.get("operator_statement") != OPERATOR_STATEMENT
        or value.get("evidence_class") != EVIDENCE_CLASS
        or value.get("independent_channel_claimed") is not True
        or value.get("independent_channel_cryptographically_verified") is not False
        or value.get("private_key_accepted") is not False
        or value.get("signer_invoked") is not False
        or value.get("scope") != "DEVELOPMENT_ONLY"
        or any(value.get(field) is not expected for field, expected in _AUTHORITY.items())
    ):
        raise ValueError("VerifierConfirmationReceiptInvalid")
    confirmed = _timestamp(value.get("confirmed_at"))
    expires = _timestamp(value.get("expires_at"))
    observed = _timestamp(observed_at)
    if expires - confirmed != VALIDITY or observed < confirmed:
        raise ValueError("VerifierConfirmationTimeInvalid")
    if observed > expires:
        raise ValueError("VerifierConfirmationExpired")
    return {
        "schema": "truepanel.aegis-verifier-confirmation-result/v1",
        "status": CONFIRMATION_STATUS,
        "release_id": RELEASE_ID,
        "source_sha256": release["source_sha256"],
        "channel": value["channel"],
        "confirmed_at": value["confirmed_at"],
        "expires_at": value["expires_at"],
        "evidence_class": EVIDENCE_CLASS,
        "independent_channel_cryptographically_verified": False,
        "scope": "DEVELOPMENT_ONLY",
        **_AUTHORITY,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build or verify an AEGIS verifier comparison attestation"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    challenge = commands.add_parser("challenge")
    challenge.add_argument("--verifier-receipt", required=True, type=Path)
    challenge.add_argument("--verifier-source", required=True, type=Path)
    confirm = commands.add_parser("confirm")
    confirm.add_argument("--challenge", required=True, type=Path)
    confirm.add_argument("--observed-sha256", required=True)
    confirm.add_argument("--channel", choices=_CHANNELS, required=True)
    confirm.add_argument("--confirmed-at", required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--receipt", required=True, type=Path)
    verify.add_argument("--verifier-receipt", required=True, type=Path)
    verify.add_argument("--verifier-source", required=True, type=Path)
    verify.add_argument("--observed-at", required=True)
    return parser


def main(arguments: list[str] | None = None) -> int:
    values = build_parser().parse_args(arguments)
    try:
        if values.command == "challenge":
            release = verify_verifier_release(
                receipt_path=values.verifier_receipt,
                source_path=values.verifier_source,
            )
            result = build_verifier_confirmation_challenge(release)
        elif values.command == "confirm":
            result = create_verifier_confirmation_receipt(
                challenge=load_verifier_confirmation_document(values.challenge),
                independently_observed_sha256=values.observed_sha256,
                channel=values.channel,
                confirmed_at=values.confirmed_at,
            )
        else:
            release = verify_verifier_release(
                receipt_path=values.verifier_receipt,
                source_path=values.verifier_source,
            )
            result = verify_verifier_confirmation_receipt(
                receipt=load_verifier_confirmation_document(values.receipt),
                release=release,
                observed_at=values.observed_at,
            )
    except ValueError as error:
        print(json.dumps({"status": "HOLD", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CHALLENGE_SCHEMA",
    "CONFIRMATION_STATUS",
    "EVIDENCE_CLASS",
    "RECEIPT_SCHEMA",
    "build_verifier_confirmation_challenge",
    "create_verifier_confirmation_receipt",
    "load_verifier_confirmation_document",
    "verifier_confirmation_challenge_sha256",
    "verify_verifier_confirmation_receipt",
]
