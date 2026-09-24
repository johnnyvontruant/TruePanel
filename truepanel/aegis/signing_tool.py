"""Public-material-only export and verification tool for AEGIS signing sessions.

This module never accepts a private key and never invokes an SSH signer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from collections.abc import Mapping, Sequence
from contextlib import suppress
from pathlib import Path
from typing import Any

from .signing_session import (
    SIGNING_SESSION_NAMESPACE,
    build_clock_witness,
    build_signing_session,
    canonical_signing_session_statement,
    verify_signing_session,
)

MATERIALS_SCHEMA = "truepanel.aegis-development-signing-materials/v1"
MANIFEST_SCHEMA = "truepanel.aegis-development-signing-kit-manifest/v1"
MAX_JSON_BYTES = 1024 * 1024
MAX_SIGNATURE_BYTES = 64 * 1024

_MATERIAL_FIELDS = {
    "schema",
    "packet",
    "unsigned_receipt",
    "policy",
    "candidate",
    "holodeck_evidence",
    "coverage_matrix",
    "reviewer_report",
}


def _read_regular(path: Path, *, maximum: int) -> bytes:
    if (
        not path.is_absolute()
        or path.is_symlink()
        or not hasattr(os, "O_NOFOLLOW")
    ):
        raise ValueError("InputPathUnsafe")
    try:
        if path.resolve(strict=True) != path:
            raise ValueError("InputPathUnsafe")
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
                raise ValueError("InputFileInvalid")
            content = b""
            while len(content) <= maximum:
                chunk = os.read(descriptor, min(65536, maximum + 1 - len(content)))
                if not chunk:
                    break
                content += chunk
            if len(content) > maximum:
                raise ValueError("InputFileInvalid")
            after = os.fstat(descriptor)
            def identity(value: os.stat_result) -> tuple[int, ...]:
                return (
                    value.st_dev,
                    value.st_ino,
                    value.st_mode,
                    value.st_size,
                    value.st_mtime_ns,
                    value.st_ctime_ns,
                )
            if identity(before) != identity(after):
                raise ValueError("InputFileChanged")
            return content
        finally:
            os.close(descriptor)
    except OSError as error:
        raise ValueError("InputFileUnavailable") from error


def load_materials(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(_read_regular(Path(path), maximum=MAX_JSON_BYTES))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("SigningMaterialsInvalid") from error
    if not isinstance(value, dict) or set(value) != _MATERIAL_FIELDS:
        raise ValueError("SigningMaterialsInvalid")
    if value.get("schema") != MATERIALS_SCHEMA:
        raise ValueError("SigningMaterialsInvalid")
    for field in _MATERIAL_FIELDS - {"schema"}:
        if not isinstance(value.get(field), dict):
            raise ValueError("SigningMaterialsInvalid")
    if value["unsigned_receipt"].get("signature") != "":
        raise ValueError("SigningMaterialsMustBeUnsigned")
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


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def export_signing_kit(
    *,
    materials_path: str | Path,
    checkout_root: str | Path,
    allowed_signers_path: str | Path,
    output_directory: str | Path,
    observed_at: str,
    unix_seconds: float,
    operator_confirmed_utc: bool,
) -> dict[str, Any]:
    """Create an immutable public signing packet outside the source checkout."""

    if operator_confirmed_utc is not True:
        raise ValueError("OperatorUtcConfirmationRequired")
    checkout = Path(checkout_root)
    try:
        if (
            not checkout.is_absolute()
            or checkout.is_symlink()
            or checkout.resolve(strict=True) != checkout
        ):
            raise ValueError("CheckoutPathUnsafe")
    except OSError as error:
        raise ValueError("CheckoutPathUnsafe") from error
    output = Path(output_directory)
    if (
        not output.is_absolute()
        or output.name in {"", ".", ".."}
        or output.is_symlink()
        or output.exists()
    ):
        raise ValueError("OutputDirectoryUnsafe")
    parent = output.parent.resolve(strict=True)
    if parent != output.parent:
        raise ValueError("OutputDirectoryUnsafe")
    proposed = parent / output.name
    if _is_within(proposed, checkout):
        raise ValueError("OutputInsideCheckoutDenied")

    materials = load_materials(materials_path)
    clock = build_clock_witness(
        observed_at=observed_at,
        unix_seconds=unix_seconds,
        confirmed_by="jt",
    )
    session = build_signing_session(
        checkout_root=checkout,
        clock_witness=clock,
        packet=materials["packet"],
        unsigned_receipt=materials["unsigned_receipt"],
        policy=materials["policy"],
        candidate=materials["candidate"],
        holodeck_evidence=materials["holodeck_evidence"],
        coverage_matrix=materials["coverage_matrix"],
        reviewer_report=materials["reviewer_report"],
        allowed_signers_path=allowed_signers_path,
    )
    statement = canonical_signing_session_statement(session)
    digest = hashlib.sha256(statement).hexdigest()
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "session_file": "aegis-development-signing-session.json",
        "session_sha256": digest,
        "signature_file": "aegis-development-signing-session.json.sig",
        "namespace": SIGNING_SESSION_NAMESPACE,
        "key_id": "jt-development-review",
        "scope": "DEVELOPMENT_ONLY",
        "production_authority": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "storage_write_authority": False,
        "automatic_promotion": False,
    }
    instructions = (
        "AEGIS DEVELOPMENT-ONLY OFFLINE SIGNING KIT\n\n"
        "1. Confirm the displayed commit, tree, UTC time, scope, and NO-authority fields.\n"
        "2. On the operator-owned signing computer, run:\n\n"
        f"   ssh-keygen -Y sign -f <JT_PRIVATE_KEY> -n {SIGNING_SESSION_NAMESPACE} "
        "aegis-development-signing-session.json\n\n"
        "3. Return only aegis-development-signing-session.json.sig.\n"
        "Never copy the private key into this directory, TruePanel, or BattleStation.\n"
        "This signature cannot authorize production, deployment, storage, network, or hardware action.\n"
    ).encode()

    created = False
    exported_files = (
        "aegis-development-signing-session.json",
        "manifest.json",
        "README.txt",
    )
    try:
        os.mkdir(proposed, 0o700)
        created = True
        _write_exclusive(proposed / "aegis-development-signing-session.json", statement)
        _write_exclusive(
            proposed / "manifest.json",
            json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(),
        )
        _write_exclusive(proposed / "README.txt", instructions)
        directory = os.open(proposed, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except (OSError, ValueError):
        if created:
            # Remove only the fixed files created by this invocation. If anything
            # else appeared concurrently, leave the directory in its fail-closed
            # occupied state for operator inspection.
            for name in exported_files:
                candidate = proposed / name
                try:
                    if candidate.is_file() and not candidate.is_symlink():
                        candidate.unlink()
                except OSError:
                    pass
            with suppress(OSError):
                proposed.rmdir()
        raise ValueError("SigningKitExportFailed") from None
    return {
        "status": "READY_FOR_OFFLINE_SIGNATURE",
        "output_directory": str(proposed),
        "session_sha256": digest,
        "namespace": SIGNING_SESSION_NAMESPACE,
        "scope": "DEVELOPMENT_ONLY",
        "production_authority": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "storage_write_authority": False,
    }


def verify_returned_signature(
    *,
    materials_path: str | Path,
    session_path: str | Path,
    signature_path: str | Path,
    checkout_root: str | Path,
    allowed_signers_path: str | Path,
) -> dict[str, Any]:
    """Verify public returned material without consuming or promoting it."""

    materials = load_materials(materials_path)
    try:
        session = json.loads(_read_regular(Path(session_path), maximum=MAX_JSON_BYTES))
        signature = _read_regular(Path(signature_path), maximum=MAX_SIGNATURE_BYTES).decode("ascii")
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("ReturnedSigningMaterialInvalid") from error
    if not isinstance(session, dict):
        raise ValueError("ReturnedSigningMaterialInvalid")
    clock = session.get("clock_witness")
    if not isinstance(clock, Mapping):
        raise ValueError("ReturnedSigningMaterialInvalid")
    return verify_signing_session(
        session=session,
        signature=signature,
        checkout_root=checkout_root,
        clock_witness=clock,
        packet=materials["packet"],
        unsigned_receipt=materials["unsigned_receipt"],
        policy=materials["policy"],
        candidate=materials["candidate"],
        holodeck_evidence=materials["holodeck_evidence"],
        coverage_matrix=materials["coverage_matrix"],
        reviewer_report=materials["reviewer_report"],
        allowed_signers_path=allowed_signers_path,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export or verify an AEGIS development signing kit")
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export", help="Export public material for offline signing")
    export.add_argument("--materials", required=True, type=Path)
    export.add_argument("--checkout", required=True, type=Path)
    export.add_argument("--allowed-signers", required=True, type=Path)
    export.add_argument("--output", required=True, type=Path)
    export.add_argument("--observed-at", required=True)
    export.add_argument("--unix-seconds", required=True, type=float)
    export.add_argument("--confirm-utc", action="store_true")
    verify = commands.add_parser("verify", help="Verify a returned detached signature")
    verify.add_argument("--materials", required=True, type=Path)
    verify.add_argument("--session", required=True, type=Path)
    verify.add_argument("--signature", required=True, type=Path)
    verify.add_argument("--checkout", required=True, type=Path)
    verify.add_argument("--allowed-signers", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.command == "export":
            result = export_signing_kit(
                materials_path=arguments.materials,
                checkout_root=arguments.checkout,
                allowed_signers_path=arguments.allowed_signers,
                output_directory=arguments.output,
                observed_at=arguments.observed_at,
                unix_seconds=arguments.unix_seconds,
                operator_confirmed_utc=arguments.confirm_utc,
            )
        else:
            result = verify_returned_signature(
                materials_path=arguments.materials,
                session_path=arguments.session,
                signature_path=arguments.signature,
                checkout_root=arguments.checkout,
                allowed_signers_path=arguments.allowed_signers,
            )
    except ValueError as error:
        print(json.dumps({"status": "HOLD", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("status") in {"READY_FOR_OFFLINE_SIGNATURE", "ELIGIBLE_FOR_DEVELOPMENT_CANDIDATE_REVIEW"} else 2


if __name__ == "__main__":
    sys.exit(main())
