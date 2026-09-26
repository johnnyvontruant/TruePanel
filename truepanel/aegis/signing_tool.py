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

from .development_review import DEVELOPMENT_NAMESPACE
from .operator_handoff import OPERATOR_HANDOFF_SCHEMA, OPERATOR_KEY_ID
from .signing_session import (
    CHECKOUT_WITNESS_SCHEMA,
    CLOCK_WITNESS_SCHEMA,
    SIGNING_SESSION_NAMESPACE,
    SIGNING_SESSION_SCHEMA,
    build_clock_witness,
    build_signing_session,
    canonical_signing_session_statement,
    verify_signing_session,
)

MATERIALS_SCHEMA = "truepanel.aegis-development-signing-materials/v1"
MANIFEST_SCHEMA = "truepanel.aegis-development-signing-kit-manifest/v2"
INDEPENDENT_WITNESS_SCHEMA = "truepanel.aegis-independent-kit-audit-witness/v1"
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

_AUTHORITY_FIELDS = {
    "production_authority": False,
    "deployment_authority": False,
    "hardware_authority": False,
    "storage_write_authority": False,
    "automatic_promotion": False,
}
_SESSION_FIELDS = {
    "schema", "handoff", "checkout_witness", "clock_witness", "receipt_sha256",
    "scope", *_AUTHORITY_FIELDS,
}
_CHECKOUT_FIELDS = {
    "schema", "commit", "tree", "clean", "submodules_clean",
    "object_replacement_disabled",
}
_CLOCK_FIELDS = {
    "schema", "source", "operator_id", "observed_at", "unix_seconds", "confirmed",
}
_HANDOFF_FIELDS = {
    "schema", "packet_sha256", "receipt_sha256_without_signature", "statement",
    "statement_sha256", "namespace", "operator_id", "key_id",
    "public_key_fingerprint", "scope",
    *_AUTHORITY_FIELDS,
}
_KIT_FILES = {
    "README.txt",
    "aegis-development-review.txt",
    "aegis-development-signing-session.json",
    "manifest.json",
}
_WITNESS_FIELDS = {
    "schema", "status", "session_sha256", "review_sha256", "manifest_sha256",
    "scope", *_AUTHORITY_FIELDS,
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


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _validate_review_session(session: Any) -> dict[str, Any]:
    """Validate only transport-visible invariants; field verification remains separate."""

    if not isinstance(session, dict) or set(session) != _SESSION_FIELDS:
        raise ValueError("SigningKitSessionInvalid")
    checkout = session.get("checkout_witness")
    clock = session.get("clock_witness")
    handoff = session.get("handoff")
    if (
        session.get("schema") != SIGNING_SESSION_SCHEMA
        or session.get("scope") != "DEVELOPMENT_ONLY"
        or not isinstance(checkout, dict)
        or set(checkout) != _CHECKOUT_FIELDS
        or not isinstance(clock, dict)
        or set(clock) != _CLOCK_FIELDS
        or not isinstance(handoff, dict)
        or set(handoff) != _HANDOFF_FIELDS
        or checkout.get("schema") != CHECKOUT_WITNESS_SCHEMA
        or clock.get("schema") != CLOCK_WITNESS_SCHEMA
        or handoff.get("schema") != OPERATOR_HANDOFF_SCHEMA
        or any(session.get(field) is not value for field, value in _AUTHORITY_FIELDS.items())
        or any(handoff.get(field) is not value for field, value in _AUTHORITY_FIELDS.items())
        or checkout.get("clean") is not True
        or checkout.get("submodules_clean") is not True
        or checkout.get("object_replacement_disabled") is not True
        or clock.get("confirmed") is not True
        or clock.get("source") != "OPERATOR_CONFIRMED_UTC"
        or clock.get("operator_id") != "jt"
        or handoff.get("operator_id") != "jt"
        or handoff.get("key_id") != OPERATOR_KEY_ID
        or handoff.get("namespace") != DEVELOPMENT_NAMESPACE
        or handoff.get("scope") != "DEVELOPMENT_ONLY"
    ):
        raise ValueError("SigningKitSessionInvalid")
    for field in ("commit", "tree"):
        value = checkout.get(field)
        if not isinstance(value, str) or len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError("SigningKitSessionInvalid")
    for field in (
        "receipt_sha256", "packet_sha256", "receipt_sha256_without_signature",
        "statement_sha256",
    ):
        value = session.get(field) if field == "receipt_sha256" else handoff.get(field)
        if not isinstance(value, str) or len(value) != 64 or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise ValueError("SigningKitSessionInvalid")
    for field in ("observed_at", "public_key_fingerprint"):
        value = clock.get(field) if field == "observed_at" else handoff.get(field)
        if not isinstance(value, str) or not value:
            raise ValueError("SigningKitSessionInvalid")
    return session


def render_operator_review(session: Mapping[str, Any]) -> bytes:
    """Render a deterministic card; the canonical session remains the signed object."""

    checked = _validate_review_session(dict(session))
    checkout = checked["checkout_witness"]
    clock = checked["clock_witness"]
    handoff = checked["handoff"]
    lines = [
        "AEGIS DEVELOPMENT-ONLY SIGNING REVIEW",
        "",
        "SIGNED OBJECT",
        f"  Commit: {checkout['commit']}",
        f"  Tree: {checkout['tree']}",
        f"  Operator-confirmed UTC: {clock['observed_at']}",
        f"  Public-key fingerprint: {handoff['public_key_fingerprint']}",
        f"  Receipt SHA-256: {checked['receipt_sha256']}",
        f"  Namespace: {SIGNING_SESSION_NAMESPACE}",
        "",
        "AUTHORITY",
        "  Scope: DEVELOPMENT_ONLY",
        "  Production authority: NO",
        "  Deployment authority: NO",
        "  Hardware authority: NO",
        "  Storage-write authority: NO",
        "  Automatic promotion: NO",
        "",
        "This card is a derived view, not the signed object.",
        "Run both independent kit audits and sign only aegis-development-signing-session.json.",
    ]
    return ("\n".join(lines) + "\n").encode()


def _instructions() -> bytes:
    return (
        "AEGIS DEVELOPMENT-ONLY OFFLINE SIGNING KIT\n\n"
        "1. Run the TruePanel audit and the standalone independent audit before trusting the review card.\n"
        "2. Require their session and review digests to agree.\n"
        "3. Compare the displayed commit, tree, UTC time, fingerprint, scope, and NO-authority fields.\n"
        "4. On the operator-owned signing computer, run:\n\n"
        f"   ssh-keygen -Y sign -f <JT_PRIVATE_KEY> -n {SIGNING_SESSION_NAMESPACE} "
        "aegis-development-signing-session.json\n\n"
        "5. Return only aegis-development-signing-session.json.sig.\n"
        "Never copy the private key into this directory, TruePanel, or BattleStation.\n"
        "This signature cannot authorize production, deployment, storage, network, or hardware action.\n"
    ).encode()


def _manifest(*, statement: bytes, review: bytes, instructions: bytes) -> dict[str, Any]:
    return {
        "schema": MANIFEST_SCHEMA,
        "session_file": "aegis-development-signing-session.json",
        "session_sha256": _sha256(statement),
        "review_file": "aegis-development-review.txt",
        "review_sha256": _sha256(review),
        "instructions_file": "README.txt",
        "instructions_sha256": _sha256(instructions),
        "signature_file": "aegis-development-signing-session.json.sig",
        "namespace": SIGNING_SESSION_NAMESPACE,
        "key_id": OPERATOR_KEY_ID,
        "scope": "DEVELOPMENT_ONLY",
        **_AUTHORITY_FIELDS,
    }


def audit_signing_kit(kit_directory: str | Path) -> dict[str, Any]:
    """Recompute every presentation file before the operator signs the session."""

    directory = Path(kit_directory)
    try:
        if (
            not directory.is_absolute()
            or directory.is_symlink()
            or directory.resolve(strict=True) != directory
            or not directory.is_dir()
        ):
            raise ValueError("SigningKitLayoutInvalid")
        with os.scandir(directory) as entries:
            if {entry.name for entry in entries} != _KIT_FILES:
                raise ValueError("SigningKitLayoutInvalid")
        statement = _read_regular(
            directory / "aegis-development-signing-session.json", maximum=MAX_JSON_BYTES
        )
        manifest_bytes = _read_regular(directory / "manifest.json", maximum=MAX_JSON_BYTES)
        review = _read_regular(
            directory / "aegis-development-review.txt", maximum=MAX_JSON_BYTES
        )
        instructions = _read_regular(directory / "README.txt", maximum=MAX_JSON_BYTES)
        session = _validate_review_session(json.loads(statement))
        canonical = canonical_signing_session_statement(session)
        manifest = json.loads(manifest_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as error:
        raise ValueError("SigningKitInvalid") from error
    if statement != canonical:
        raise ValueError("SigningKitSessionNotCanonical")
    expected_review = render_operator_review(session)
    expected_instructions = _instructions()
    expected_manifest = _manifest(
        statement=canonical, review=expected_review, instructions=expected_instructions
    )
    canonical_manifest = json.dumps(
        expected_manifest, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    if (
        review != expected_review
        or instructions != expected_instructions
        or manifest != expected_manifest
        or manifest_bytes != canonical_manifest
    ):
        raise ValueError("SigningKitPresentationMismatch")
    return {
        "status": "INTERNAL_AUDIT_PASS",
        "session_sha256": expected_manifest["session_sha256"],
        "review_sha256": expected_manifest["review_sha256"],
        "manifest_sha256": _sha256(canonical_manifest),
        "namespace": SIGNING_SESSION_NAMESPACE,
        "scope": "DEVELOPMENT_ONLY",
        **_AUTHORITY_FIELDS,
    }


def dual_audit_signing_kit(
    kit_directory: str | Path, independent_witness_path: str | Path
) -> dict[str, Any]:
    """Require digest-identical verdicts from TruePanel and the standalone auditor."""

    internal = audit_signing_kit(kit_directory)
    try:
        witness_bytes = _read_regular(
            Path(independent_witness_path), maximum=MAX_JSON_BYTES
        )
        witness = json.loads(witness_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("IndependentAuditWitnessInvalid") from error
    canonical = json.dumps(
        witness, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    if (
        not isinstance(witness, dict)
        or set(witness) != _WITNESS_FIELDS
        or witness_bytes != canonical
        or witness.get("schema") != INDEPENDENT_WITNESS_SCHEMA
        or witness.get("status") != "INDEPENDENT_AUDIT_PASS"
        or witness.get("scope") != "DEVELOPMENT_ONLY"
        or any(witness.get(field) is not value for field, value in _AUTHORITY_FIELDS.items())
        or any(
            witness.get(field) != internal.get(field)
            for field in ("session_sha256", "review_sha256", "manifest_sha256")
        )
    ):
        raise ValueError("IndependentAuditWitnessMismatch")
    return {
        "status": "READY_FOR_OPERATOR_SIGNATURE",
        "session_sha256": internal["session_sha256"],
        "review_sha256": internal["review_sha256"],
        "manifest_sha256": internal["manifest_sha256"],
        "auditors_agree": True,
        "scope": "DEVELOPMENT_ONLY",
        **_AUTHORITY_FIELDS,
    }


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
    digest = _sha256(statement)
    review = render_operator_review(session)
    instructions = _instructions()
    manifest = _manifest(statement=statement, review=review, instructions=instructions)

    created = False
    exported_files = (
        "aegis-development-signing-session.json",
        "aegis-development-review.txt",
        "manifest.json",
        "README.txt",
    )
    try:
        os.mkdir(proposed, 0o700)
        created = True
        _write_exclusive(proposed / "aegis-development-signing-session.json", statement)
        _write_exclusive(proposed / "aegis-development-review.txt", review)
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
        audit_signing_kit(proposed)
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
        "status": "READY_FOR_DUAL_AUDIT",
        "output_directory": str(proposed),
        "session_sha256": digest,
        "review_sha256": _sha256(review),
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
    parser = argparse.ArgumentParser(description="Export, audit, or verify an AEGIS development signing kit")
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export", help="Export public material for offline signing")
    export.add_argument("--materials", required=True, type=Path)
    export.add_argument("--checkout", required=True, type=Path)
    export.add_argument("--allowed-signers", required=True, type=Path)
    export.add_argument("--output", required=True, type=Path)
    export.add_argument("--observed-at", required=True)
    export.add_argument("--unix-seconds", required=True, type=float)
    export.add_argument("--confirm-utc", action="store_true")
    audit = commands.add_parser("audit", help="Audit a public kit before signing")
    audit.add_argument("--kit", required=True, type=Path)
    dual_audit = commands.add_parser(
        "dual-audit", help="Require TruePanel and an independent witness to agree"
    )
    dual_audit.add_argument("--kit", required=True, type=Path)
    dual_audit.add_argument("--independent-witness", required=True, type=Path)
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
        elif arguments.command == "audit":
            result = audit_signing_kit(arguments.kit)
        elif arguments.command == "dual-audit":
            result = dual_audit_signing_kit(
                arguments.kit, arguments.independent_witness
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
    return 0 if result.get("status") in {
        "READY_FOR_DUAL_AUDIT", "INTERNAL_AUDIT_PASS", "READY_FOR_OPERATOR_SIGNATURE",
        "ELIGIBLE_FOR_DEVELOPMENT_CANDIDATE_REVIEW",
    } else 2


if __name__ == "__main__":
    sys.exit(main())
