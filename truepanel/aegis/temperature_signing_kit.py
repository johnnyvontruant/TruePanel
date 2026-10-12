"""Public-only export and return verification for temperature acceptance.

This module deliberately has no signing function and accepts no private-key
input.  It exports the exact canonical statement for an operator-controlled
offline signer, then verifies the returned detached SSHSIG against a protected
public roster through a caller-supplied verifier.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from contextlib import suppress
from pathlib import Path
from typing import Any, Final

from .temperature_authenticated_acceptance import (
    KEY_ID,
    NAMESPACE,
    STATUS_AUTHENTICATED,
    build_temperature_acceptance_statement,
    evaluate_authenticated_temperature_acceptance,
)

KIT_SCHEMA: Final = "truepanel.aegis-temperature-signing-kit/v1"
RESULT_SCHEMA: Final = "truepanel.aegis-temperature-signing-checkride/v1"
STATUS_READY: Final = "READY_FOR_OFFLINE_OPERATOR_SIGNATURE"
STATUS_HOLD: Final = "HOLD"
MAX_PUBLIC_FILE_BYTES: Final = 128 * 1024
MAX_SIGNATURE_BYTES: Final = 32 * 1024
_FILES: Final = ("statement.json", "manifest.json", "SIGNING.txt")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _write_new(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise ValueError("NoFollowUnavailable")
    descriptor = os.open(path, flags | no_follow, 0o600)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("PublicKitWriteFailed")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _snapshot(path: Path, maximum: int) -> bytes:
    if not path.is_absolute() or not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("ProtectedFileUnavailable")
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("ProtectedFileNotRegular")
        if before.st_uid != os.geteuid() or before.st_mode & 0o022:
            raise ValueError("ProtectedFilePermissionsInvalid")
        if before.st_size <= 0 or before.st_size > maximum:
            raise ValueError("ProtectedFileSizeInvalid")
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        identity = lambda value: (  # noqa: E731 - local comparison helper
            value.st_dev,
            value.st_ino,
            value.st_mode,
            value.st_uid,
            value.st_size,
            value.st_mtime_ns,
            value.st_ctime_ns,
        )
        if identity(before) != identity(after):
            raise ValueError("ProtectedFileChanged")
        if not payload or len(payload) > maximum:
            raise ValueError("ProtectedFileSizeInvalid")
        return payload
    finally:
        os.close(descriptor)


def _instructions(statement_sha256: str) -> bytes:
    return (
        "AEGIS TEMPERATURE DEVELOPMENT REVIEW - PUBLIC SIGNING KIT\n"
        f"Statement SHA-256: {statement_sha256}\n"
        f"SSHSIG namespace: {NAMESPACE}\n"
        f"Signer identity: {KEY_ID}\n"
        "Keep the private key outside TruePanel. Sign statement.json offline.\n"
        "Return only the detached ASCII-armored SSHSIG file.\n"
        "This signature grants development-review eligibility only.\n"
        "It grants no install, deploy, storage, network, or hardware authority.\n"
    ).encode("ascii")


def export_temperature_signing_kit(
    candidate: dict[str, Any],
    appraisal: dict[str, Any],
    confirmation: dict[str, Any],
    output_directory: str | Path,
    *,
    source_root: str | Path,
    now_utc: str,
) -> dict[str, Any]:
    """Export three public files atomically enough to fail closed on error."""

    output = Path(output_directory)
    source = Path(source_root)
    errors: list[str] = []
    created = False
    manifest: dict[str, Any] = {}
    try:
        if not output.is_absolute() or not source.is_absolute():
            raise ValueError("AbsolutePathsRequired")
        if source.is_symlink():
            raise ValueError("SourceCheckoutSymlinkInvalid")
        resolved_source = source.resolve(strict=True)
        resolved_parent = output.parent.resolve(strict=True)
        projected = resolved_parent / output.name
        if output.is_symlink() or _inside(projected, resolved_source):
            raise ValueError("KitMustBeOutsideSourceCheckout")
        if output.exists():
            raise ValueError("KitOutputAlreadyExists")
        statement = build_temperature_acceptance_statement(
            candidate, appraisal, confirmation, now_utc=now_utc
        )
        statement_digest = _sha256(statement)
        instructions = _instructions(statement_digest)
        manifest = {
            "schema": KIT_SCHEMA,
            "key_id": KEY_ID,
            "namespace": NAMESPACE,
            "scope": "development-candidate-review-only",
            "statement_sha256": statement_digest,
            "instructions_sha256": _sha256(instructions),
            "accepted": False,
            "installed": False,
            "deployment_authority": False,
            "hardware_authority": False,
            "private_key_expected": False,
        }
        output.mkdir(mode=0o700)
        created = True
        _write_new(output / "statement.json", statement)
        _write_new(output / "manifest.json", _canonical(manifest) + b"\n")
        _write_new(output / "SIGNING.txt", instructions)
        directory_descriptor = os.open(output, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except (FileNotFoundError, OSError, TypeError, ValueError) as error:
        errors.append(str(error) or error.__class__.__name__)
        if created:
            for name in _FILES:
                with suppress(FileNotFoundError):
                    (output / name).unlink()
            with suppress(OSError):
                output.rmdir()

    ready = not errors
    result = {
        "schema": RESULT_SCHEMA,
        "status": STATUS_READY if ready else STATUS_HOLD,
        "kit_created": ready,
        "file_count": len(_FILES) if ready else 0,
        "manifest": manifest if ready else None,
        "errors": errors,
        "private_key_accepted": False,
        "signer_invoked": False,
        "accepted": False,
        "installed": False,
        "deployment_authority": False,
        "hardware_authority": False,
    }
    result["record_sha256"] = _sha256(_canonical(result))
    return result


def verify_temperature_signing_return(
    candidate: dict[str, Any],
    appraisal: dict[str, Any],
    confirmation: dict[str, Any],
    kit_directory: str | Path,
    signature_path: str | Path,
    verifier: Any,
    *,
    now_utc: str,
) -> dict[str, Any]:
    """Reconstruct the kit and verify a protected detached signature."""

    kit = Path(kit_directory)
    errors: list[str] = []
    authentication: dict[str, Any] | None = None
    try:
        if not kit.is_absolute() or kit.is_symlink():
            raise ValueError("ProtectedKitUnavailable")
        if {item.name for item in kit.iterdir()} != set(_FILES):
            raise ValueError("PublicKitFileSetInvalid")
        statement = _snapshot(kit / "statement.json", MAX_PUBLIC_FILE_BYTES)
        manifest_payload = _snapshot(kit / "manifest.json", MAX_PUBLIC_FILE_BYTES)
        instructions = _snapshot(kit / "SIGNING.txt", MAX_PUBLIC_FILE_BYTES)
        expected_statement = build_temperature_acceptance_statement(
            candidate, appraisal, confirmation, now_utc=now_utc
        )
        expected_manifest = {
            "schema": KIT_SCHEMA,
            "key_id": KEY_ID,
            "namespace": NAMESPACE,
            "scope": "development-candidate-review-only",
            "statement_sha256": _sha256(expected_statement),
            "instructions_sha256": _sha256(_instructions(_sha256(expected_statement))),
            "accepted": False,
            "installed": False,
            "deployment_authority": False,
            "hardware_authority": False,
            "private_key_expected": False,
        }
        if statement != expected_statement:
            raise ValueError("SigningStatementMismatch")
        if manifest_payload != _canonical(expected_manifest) + b"\n":
            raise ValueError("SigningManifestMismatch")
        if instructions != _instructions(_sha256(expected_statement)):
            raise ValueError("SigningInstructionsMismatch")
        signature = _snapshot(Path(signature_path), MAX_SIGNATURE_BYTES).decode("ascii")
        authentication = evaluate_authenticated_temperature_acceptance(
            candidate,
            appraisal,
            confirmation,
            signature,
            verifier,
            now_utc=now_utc,
        )
        if authentication["status"] != STATUS_AUTHENTICATED:
            raise ValueError("ReturnedSignatureNotAuthenticated")
    except (
        FileNotFoundError,
        NotADirectoryError,
        OSError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
    ) as error:
        errors.append(str(error) or error.__class__.__name__)

    authenticated = not errors and authentication is not None
    result = {
        "schema": RESULT_SCHEMA,
        "status": STATUS_AUTHENTICATED if authenticated else STATUS_HOLD,
        "operator_signature_verified": authenticated,
        "development_review_accepted": authenticated,
        "authentication_record_sha256": authentication.get("record_sha256")
        if authenticated
        else None,
        "errors": errors,
        "private_key_accepted": False,
        "signer_invoked": False,
        "accepted": False,
        "installed": False,
        "runtime_authority": False,
        "production_authority": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "storage_write_authority": False,
        "network_authority": False,
        "automatic_promotion": False,
    }
    result["record_sha256"] = _sha256(_canonical(result))
    return result


__all__ = [
    "STATUS_READY",
    "export_temperature_signing_kit",
    "verify_temperature_signing_return",
]
