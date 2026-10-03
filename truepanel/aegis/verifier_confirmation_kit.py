"""Public-only custody kit for the verifier comparison ceremony.

The kit makes the exact challenge reviewable on another operator-controlled
device.  It never accepts private material, invokes a signer, or proves that
its delivery channel was independent.
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
    CHALLENGE_SCHEMA,
    build_verifier_confirmation_challenge,
    create_verifier_confirmation_receipt,
    verifier_confirmation_challenge_sha256,
)

MANIFEST_SCHEMA = "truepanel.aegis-verifier-confirmation-kit-manifest/v1"
KIT_STATUS = "READY_FOR_OPERATOR_COMPARISON"
MAX_FILE_BYTES = 1024 * 1024
KIT_FILES = {
    "aegis-verifier-challenge.json",
    "aegis-verifier-comparison.txt",
    "manifest.json",
}
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
        raise ValueError("VerifierConfirmationKitUnsafePath")
    try:
        if path.resolve(strict=True) != path:
            raise ValueError("VerifierConfirmationKitUnsafePath")
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            before = os.fstat(descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_size <= 0
                or before.st_size > MAX_FILE_BYTES
            ):
                raise ValueError("VerifierConfirmationKitInvalidFile")
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
        raise ValueError("VerifierConfirmationKitUnavailable") from error
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
        raise ValueError("VerifierConfirmationKitChanged")
    return content


def render_verifier_comparison_card(challenge: Mapping[str, Any]) -> bytes:
    """Render the complete digest and the limits of the human attestation."""

    value = dict(challenge)
    blocks = value.get("fingerprint_blocks")
    channels = value.get("allowed_channels")
    if (
        value.get("schema") != CHALLENGE_SCHEMA
        or not isinstance(blocks, list)
        or len(blocks) != 8
        or any(not isinstance(block, str) or len(block) != 8 for block in blocks)
        or "".join(blocks) != value.get("source_sha256")
        or not isinstance(channels, list)
        or not channels
    ):
        raise ValueError("VerifierConfirmationChallengeInvalid")
    lines = [
        "AEGIS DEVELOPMENT-ONLY VERIFIER COMPARISON",
        "",
        f"Release: {value['release_id']}",
        f"Verifier commit: {value['source_commit']}",
        "Verifier SHA-256:",
        f"  {' '.join(blocks[:4])}",
        f"  {' '.join(blocks[4:])}",
        f"Challenge SHA-256: {verifier_confirmation_challenge_sha256(value)}",
        "",
        "APPROVED OUT-OF-BAND METHODS",
        *[f"  - {channel}" for channel in channels],
        "",
        "BOUNDARY",
        "  Compare every digest block with a value obtained through one approved method.",
        "  This kit is not the independent source and cannot prove its own delivery path.",
        "  A resulting attestation expires after 30 minutes and is not cryptographic proof.",
        "  Production, deployment, hardware, and storage authority: NO.",
        "",
    ]
    return "\n".join(lines).encode()


def _manifest(challenge: bytes, card: bytes) -> dict[str, Any]:
    return {
        "schema": MANIFEST_SCHEMA,
        "status": KIT_STATUS,
        "challenge_file": "aegis-verifier-challenge.json",
        "challenge_sha256": _sha256(challenge),
        "comparison_file": "aegis-verifier-comparison.txt",
        "comparison_sha256": _sha256(card),
        "operator_id": "jt",
        "private_key_requested": False,
        "signer_invoked": False,
        "independent_channel_cryptographically_verified": False,
        "scope": "DEVELOPMENT_ONLY",
        **_AUTHORITY,
    }


def export_verifier_confirmation_kit(
    *,
    verifier_receipt_path: str | Path,
    verifier_source_path: str | Path,
    output_directory: str | Path,
) -> dict[str, Any]:
    """Atomically export the public comparison materials to a new directory."""

    release = verify_verifier_release(
        receipt_path=verifier_receipt_path, source_path=verifier_source_path
    )
    challenge_value = build_verifier_confirmation_challenge(release)
    challenge = _canonical(challenge_value)
    card = render_verifier_comparison_card(challenge_value)
    manifest_value = _manifest(challenge, card)
    manifest = _canonical(manifest_value)
    output = Path(output_directory)
    if not output.is_absolute() or output.is_symlink() or output.exists():
        raise ValueError("VerifierConfirmationKitOutputUnsafe")
    parent = output.parent.resolve(strict=True)
    if not parent.is_dir() or parent.is_symlink():
        raise ValueError("VerifierConfirmationKitOutputUnsafe")
    created = False
    try:
        output.mkdir(mode=0o700)
        created = True
        _write_exclusive(output / "aegis-verifier-challenge.json", challenge)
        _write_exclusive(output / "aegis-verifier-comparison.txt", card)
        _write_exclusive(output / "manifest.json", manifest)
    except (OSError, ValueError) as error:
        if created:
            for name in KIT_FILES:
                with suppress(OSError):
                    (output / name).unlink()
            with suppress(OSError):
                output.rmdir()
        raise ValueError("VerifierConfirmationKitExportFailed") from error
    return audit_verifier_confirmation_kit(output)


def audit_verifier_confirmation_kit(directory: str | Path) -> dict[str, Any]:
    """Reconstruct all three files instead of trusting the manifest as a root."""

    root = Path(directory)
    if not root.is_absolute() or root.is_symlink():
        raise ValueError("VerifierConfirmationKitUnsafePath")
    try:
        if root.resolve(strict=True) != root or not root.is_dir():
            raise ValueError("VerifierConfirmationKitUnsafePath")
        entries = {item.name for item in root.iterdir()}
    except OSError as error:
        raise ValueError("VerifierConfirmationKitUnavailable") from error
    if entries != KIT_FILES:
        raise ValueError("VerifierConfirmationKitFileSetInvalid")
    challenge_bytes = _read_regular(root / "aegis-verifier-challenge.json")
    card = _read_regular(root / "aegis-verifier-comparison.txt")
    manifest_bytes = _read_regular(root / "manifest.json")
    try:
        challenge = json.loads(challenge_bytes)
        manifest = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("VerifierConfirmationKitJsonInvalid") from error
    if isinstance(challenge, dict):
        try:
            create_verifier_confirmation_receipt(
                challenge=challenge,
                independently_observed_sha256=str(challenge.get("source_sha256", "")),
                channel=str((challenge.get("allowed_channels") or [""])[0]),
                confirmed_at="1970-01-01T00:00:00Z",
            )
        except (IndexError, TypeError, ValueError) as error:
            raise ValueError("VerifierConfirmationKitMismatch") from error
    if (
        not isinstance(challenge, dict)
        or not isinstance(manifest, dict)
        or challenge_bytes != _canonical(challenge)
        or manifest_bytes != _canonical(manifest)
        or card != render_verifier_comparison_card(challenge)
        or manifest != _manifest(challenge_bytes, card)
    ):
        raise ValueError("VerifierConfirmationKitMismatch")
    return {
        "schema": "truepanel.aegis-verifier-confirmation-kit-audit/v1",
        "status": KIT_STATUS,
        "challenge": challenge,
        "challenge_sha256": verifier_confirmation_challenge_sha256(challenge),
        "comparison_sha256": _sha256(card),
        "manifest_sha256": _sha256(manifest_bytes),
        "private_key_accepted": False,
        "signer_invoked": False,
        "independent_channel_cryptographically_verified": False,
        "scope": "DEVELOPMENT_ONLY",
        **_AUTHORITY,
    }


def confirm_from_verifier_confirmation_kit(
    *,
    directory: str | Path,
    independently_observed_sha256: str,
    channel: str,
    confirmed_at: str,
) -> dict[str, Any]:
    """Audit the exact human presentation before creating its short-lived receipt."""

    audit = audit_verifier_confirmation_kit(directory)
    return create_verifier_confirmation_receipt(
        challenge=audit["challenge"],
        independently_observed_sha256=independently_observed_sha256,
        channel=channel,
        confirmed_at=confirmed_at,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export or audit an AEGIS comparison kit")
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export")
    export.add_argument("--verifier-receipt", required=True, type=Path)
    export.add_argument("--verifier-source", required=True, type=Path)
    export.add_argument("--output", required=True, type=Path)
    audit = commands.add_parser("audit")
    audit.add_argument("--kit", required=True, type=Path)
    confirm = commands.add_parser("confirm")
    confirm.add_argument("--kit", required=True, type=Path)
    confirm.add_argument("--observed-sha256", required=True)
    confirm.add_argument("--channel", required=True)
    confirm.add_argument("--confirmed-at", required=True)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    values = build_parser().parse_args(arguments)
    try:
        if values.command == "export":
            result = export_verifier_confirmation_kit(
                verifier_receipt_path=values.verifier_receipt,
                verifier_source_path=values.verifier_source,
                output_directory=values.output,
            )
        elif values.command == "audit":
            result = audit_verifier_confirmation_kit(values.kit)
        else:
            result = confirm_from_verifier_confirmation_kit(
                directory=values.kit,
                independently_observed_sha256=values.observed_sha256,
                channel=values.channel,
                confirmed_at=values.confirmed_at,
            )
    except ValueError as error:
        print(json.dumps({"status": "HOLD", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "KIT_STATUS",
    "MANIFEST_SCHEMA",
    "audit_verifier_confirmation_kit",
    "confirm_from_verifier_confirmation_kit",
    "export_verifier_confirmation_kit",
    "render_verifier_comparison_card",
]
