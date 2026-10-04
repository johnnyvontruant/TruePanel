"""Custody-safe handoff for a short-lived verifier confirmation receipt.

The handoff persists only public operator-attestation material.  It binds the
receipt back to the exact release-pinned comparison kit, never accepts private
material, and cannot prove that the operator's comparison channel was
independent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from collections.abc import Mapping, Sequence
from contextlib import suppress
from pathlib import Path
from typing import Any

from .verifier_bootstrap import verify_verifier_release
from .verifier_confirmation import (
    EVIDENCE_CLASS,
    create_verifier_confirmation_receipt,
    verify_verifier_confirmation_receipt,
)
from .verifier_confirmation_kit import audit_verifier_confirmation_kit

HANDOFF_SCHEMA = "truepanel.aegis-verifier-confirmation-handoff-manifest/v1"
HANDOFF_STATUS = "VERIFIER_CONFIRMATION_HANDOFF_VERIFIED"
HANDOFF_FILES = {"aegis-verifier-confirmation-receipt.json", "manifest.json"}
MAX_FILE_BYTES = 1024 * 1024
_AUTHORITY = {
    "production_authority": False,
    "deployment_authority": False,
    "hardware_authority": False,
    "storage_write_authority": False,
    "automatic_promotion": False,
}


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode() + b"\n"


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("VerifierConfirmationHandoffDuplicateJsonKey")
        value[key] = item
    return value


def _write_exclusive(path: Path, content: bytes) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_regular(path: Path) -> bytes:
    if not path.is_absolute() or path.is_symlink() or not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("VerifierConfirmationHandoffUnsafePath")
    try:
        if path.resolve(strict=True) != path:
            raise ValueError("VerifierConfirmationHandoffUnsafePath")
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            before = os.fstat(descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_size <= 0
                or before.st_size > MAX_FILE_BYTES
            ):
                raise ValueError("VerifierConfirmationHandoffInvalidFile")
            content = b""
            while len(content) <= MAX_FILE_BYTES:
                chunk = os.read(
                    descriptor, min(65536, MAX_FILE_BYTES + 1 - len(content))
                )
                if not chunk:
                    break
                content += chunk
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise ValueError("VerifierConfirmationHandoffUnavailable") from error

    def identity(value: os.stat_result) -> tuple[int, ...]:
        return (
            value.st_dev,
            value.st_ino,
            value.st_mode,
            value.st_size,
            value.st_mtime_ns,
            value.st_ctime_ns,
        )

    if len(content) > MAX_FILE_BYTES or identity(before) != identity(after):
        raise ValueError("VerifierConfirmationHandoffChanged")
    return content


def _manifest(
    *, receipt: bytes, kit_audit: Mapping[str, Any], receipt_value: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "schema": HANDOFF_SCHEMA,
        "status": HANDOFF_STATUS,
        "receipt_file": "aegis-verifier-confirmation-receipt.json",
        "receipt_sha256": _sha256(receipt),
        "kit_challenge_sha256": kit_audit["challenge_sha256"],
        "kit_comparison_sha256": kit_audit["comparison_sha256"],
        "kit_manifest_sha256": kit_audit["manifest_sha256"],
        "source_commit": receipt_value["source_commit"],
        "source_sha256": receipt_value["source_sha256"],
        "confirmed_at": receipt_value["confirmed_at"],
        "expires_at": receipt_value["expires_at"],
        "operator_id": "jt",
        "evidence_class": EVIDENCE_CLASS,
        "independent_channel_cryptographically_verified": False,
        "private_key_accepted": False,
        "signer_invoked": False,
        "scope": "DEVELOPMENT_ONLY",
        **_AUTHORITY,
    }


def stage_verifier_confirmation_handoff(
    *,
    kit_directory: str | Path,
    verifier_receipt_path: str | Path,
    verifier_source_path: str | Path,
    independently_observed_sha256: str,
    channel: str,
    confirmed_at: str,
    output_directory: str | Path,
) -> dict[str, Any]:
    """Create a new owner-protected public receipt handoff without overwriting."""

    kit_audit = audit_verifier_confirmation_kit(
        kit_directory,
        verifier_receipt_path=verifier_receipt_path,
        verifier_source_path=verifier_source_path,
    )
    receipt_value = create_verifier_confirmation_receipt(
        challenge=kit_audit["challenge"],
        independently_observed_sha256=independently_observed_sha256,
        channel=channel,
        confirmed_at=confirmed_at,
    )
    receipt = _canonical(receipt_value)
    manifest = _canonical(
        _manifest(receipt=receipt, kit_audit=kit_audit, receipt_value=receipt_value)
    )
    output = Path(output_directory)
    if not output.is_absolute() or output.is_symlink() or output.exists():
        raise ValueError("VerifierConfirmationHandoffOutputUnsafe")
    parent = output.parent.resolve(strict=True)
    if not parent.is_dir() or parent.is_symlink():
        raise ValueError("VerifierConfirmationHandoffOutputUnsafe")
    created = False
    try:
        output.mkdir(mode=0o700)
        created = True
        _write_exclusive(output / "aegis-verifier-confirmation-receipt.json", receipt)
        _write_exclusive(output / "manifest.json", manifest)
    except (OSError, ValueError) as error:
        if created:
            for name in HANDOFF_FILES:
                with suppress(OSError):
                    (output / name).unlink()
            with suppress(OSError):
                output.rmdir()
        raise ValueError("VerifierConfirmationHandoffExportFailed") from error
    return audit_verifier_confirmation_handoff(
        handoff_directory=output,
        kit_directory=kit_directory,
        verifier_receipt_path=verifier_receipt_path,
        verifier_source_path=verifier_source_path,
        observed_at=confirmed_at,
    )


def audit_verifier_confirmation_handoff(
    *,
    handoff_directory: str | Path,
    kit_directory: str | Path,
    verifier_receipt_path: str | Path,
    verifier_source_path: str | Path,
    observed_at: str,
) -> dict[str, Any]:
    """Reconstruct the handoff, pinned release, kit, receipt, and expiry."""

    root = Path(handoff_directory)
    if not root.is_absolute() or root.is_symlink():
        raise ValueError("VerifierConfirmationHandoffUnsafePath")
    try:
        if root.resolve(strict=True) != root or not root.is_dir():
            raise ValueError("VerifierConfirmationHandoffUnsafePath")
        entries = {item.name for item in root.iterdir()}
    except OSError as error:
        raise ValueError("VerifierConfirmationHandoffUnavailable") from error
    if entries != HANDOFF_FILES:
        raise ValueError("VerifierConfirmationHandoffFileSetInvalid")
    receipt_path = root / "aegis-verifier-confirmation-receipt.json"
    receipt_bytes = _read_regular(receipt_path)
    manifest_bytes = _read_regular(root / "manifest.json")
    try:
        receipt = json.loads(receipt_bytes, object_pairs_hook=_no_duplicate_keys)
        manifest = json.loads(manifest_bytes, object_pairs_hook=_no_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("VerifierConfirmationHandoffJsonInvalid") from error
    if not isinstance(receipt, dict) or receipt_bytes != _canonical(receipt):
        raise ValueError("VerifierConfirmationHandoffJsonInvalid")
    kit_audit = audit_verifier_confirmation_kit(
        kit_directory,
        verifier_receipt_path=verifier_receipt_path,
        verifier_source_path=verifier_source_path,
    )
    release = verify_verifier_release(
        receipt_path=verifier_receipt_path,
        source_path=verifier_source_path,
    )
    verified = verify_verifier_confirmation_receipt(
        receipt=receipt,
        release=release,
        observed_at=observed_at,
    )
    expected_receipt = create_verifier_confirmation_receipt(
        challenge=kit_audit["challenge"],
        independently_observed_sha256=str(receipt.get("source_sha256", "")),
        channel=str(receipt.get("channel", "")),
        confirmed_at=str(receipt.get("confirmed_at", "")),
    )
    if (
        receipt != expected_receipt
        or receipt_bytes != _canonical(receipt)
        or not isinstance(manifest, dict)
        or manifest_bytes != _canonical(manifest)
        or manifest
        != _manifest(receipt=receipt_bytes, kit_audit=kit_audit, receipt_value=receipt)
    ):
        raise ValueError("VerifierConfirmationHandoffMismatch")
    return {
        "schema": "truepanel.aegis-verifier-confirmation-handoff-result/v1",
        "status": HANDOFF_STATUS,
        "receipt": receipt,
        "receipt_sha256": _sha256(receipt_bytes),
        "kit_challenge_sha256": kit_audit["challenge_sha256"],
        "source_sha256": verified["source_sha256"],
        "confirmed_at": verified["confirmed_at"],
        "expires_at": verified["expires_at"],
        "evidence_class": EVIDENCE_CLASS,
        "independent_channel_cryptographically_verified": False,
        "private_key_accepted": False,
        "signer_invoked": False,
        "scope": "DEVELOPMENT_ONLY",
        **_AUTHORITY,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Stage or audit an AEGIS verifier confirmation handoff"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("stage", "audit"):
        command = commands.add_parser(name)
        command.add_argument("--kit", required=True, type=Path)
        command.add_argument("--verifier-receipt", required=True, type=Path)
        command.add_argument("--verifier-source", required=True, type=Path)
        command.add_argument("--handoff", required=True, type=Path)
        if name == "stage":
            command.add_argument("--observed-sha256", required=True)
            command.add_argument("--channel", required=True)
            command.add_argument("--confirmed-at", required=True)
        else:
            command.add_argument("--observed-at", required=True)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    values = build_parser().parse_args(arguments)
    try:
        if values.command == "stage":
            result = stage_verifier_confirmation_handoff(
                kit_directory=values.kit,
                verifier_receipt_path=values.verifier_receipt,
                verifier_source_path=values.verifier_source,
                independently_observed_sha256=values.observed_sha256,
                channel=values.channel,
                confirmed_at=values.confirmed_at,
                output_directory=values.handoff,
            )
        else:
            result = audit_verifier_confirmation_handoff(
                handoff_directory=values.handoff,
                kit_directory=values.kit,
                verifier_receipt_path=values.verifier_receipt,
                verifier_source_path=values.verifier_source,
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
    "HANDOFF_SCHEMA",
    "HANDOFF_STATUS",
    "audit_verifier_confirmation_handoff",
    "stage_verifier_confirmation_handoff",
]
