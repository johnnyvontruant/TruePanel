#!/usr/bin/env python3
"""Standalone, read-only verifier for an AEGIS development signing kit.

This file deliberately uses only the Python standard library and imports no
TruePanel module.  Run it from an independently pinned checkout with ``-I``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

SESSION_SCHEMA = "truepanel.aegis-development-signing-session/v1"
HANDOFF_SCHEMA = "truepanel.aegis-development-operator-handoff/v1"
CHECKOUT_SCHEMA = "truepanel.aegis-clean-checkout-witness/v1"
CLOCK_SCHEMA = "truepanel.aegis-operator-clock-witness/v1"
MANIFEST_SCHEMA = "truepanel.aegis-development-signing-kit-manifest/v2"
WITNESS_SCHEMA = "truepanel.aegis-independent-kit-audit-witness/v1"
SESSION_NAMESPACE = "truepanel-aegis-development-signing-session-v1@truepanel"
DEVELOPMENT_NAMESPACE = "truepanel-aegis-development-review-v1@truepanel"
KEY_ID = "jt-development-review"
MAX_BYTES = 1024 * 1024

AUTHORITY = {
    "production_authority": False,
    "deployment_authority": False,
    "hardware_authority": False,
    "storage_write_authority": False,
    "automatic_promotion": False,
}
KIT_FILES = {
    "README.txt",
    "aegis-development-review.txt",
    "aegis-development-signing-session.json",
    "manifest.json",
}
SESSION_FIELDS = {
    "schema", "handoff", "checkout_witness", "clock_witness", "receipt_sha256",
    "scope", *AUTHORITY,
}
CHECKOUT_FIELDS = {
    "schema", "commit", "tree", "clean", "submodules_clean",
    "object_replacement_disabled",
}
CLOCK_FIELDS = {
    "schema", "source", "operator_id", "observed_at", "unix_seconds", "confirmed",
}
HANDOFF_FIELDS = {
    "schema", "packet_sha256", "receipt_sha256_without_signature", "statement",
    "statement_sha256", "namespace", "operator_id", "key_id",
    "public_key_fingerprint", "scope", *AUTHORITY,
}
MANIFEST_FIELDS = {
    "schema", "session_file", "session_sha256", "review_file", "review_sha256",
    "instructions_file", "instructions_sha256", "signature_file", "namespace",
    "key_id", "scope", *AUTHORITY,
}


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("IndependentAuditDuplicateJsonKey")
        result[key] = value
    return result


def _read_regular(path: Path) -> bytes:
    if not path.is_absolute() or path.is_symlink() or not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("IndependentAuditUnsafePath")
    try:
        if path.resolve(strict=True) != path:
            raise ValueError("IndependentAuditUnsafePath")
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_BYTES:
                raise ValueError("IndependentAuditInvalidFile")
            content = b""
            while len(content) <= MAX_BYTES:
                chunk = os.read(descriptor, min(65536, MAX_BYTES + 1 - len(content)))
                if not chunk:
                    break
                content += chunk
            after = os.fstat(descriptor)
            def identity(value: os.stat_result) -> tuple[int, ...]:
                return (
                    value.st_dev, value.st_ino, value.st_mode, value.st_size,
                    value.st_mtime_ns, value.st_ctime_ns,
                )
            if len(content) > MAX_BYTES or identity(before) != identity(after):
                raise ValueError("IndependentAuditChangingFile")
            return content
        finally:
            os.close(descriptor)
    except OSError as error:
        raise ValueError("IndependentAuditUnavailableFile") from error


def _json(content: bytes) -> Any:
    try:
        return json.loads(content, object_pairs_hook=_no_duplicates)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("IndependentAuditInvalidJson") from error


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _hex(value: Any, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value)
    )


def _validate_session(session: Any) -> dict[str, Any]:
    if not isinstance(session, dict) or set(session) != SESSION_FIELDS:
        raise ValueError("IndependentAuditSessionInvalid")
    checkout = session.get("checkout_witness")
    clock = session.get("clock_witness")
    handoff = session.get("handoff")
    if (
        session.get("schema") != SESSION_SCHEMA
        or session.get("scope") != "DEVELOPMENT_ONLY"
        or not isinstance(checkout, dict) or set(checkout) != CHECKOUT_FIELDS
        or not isinstance(clock, dict) or set(clock) != CLOCK_FIELDS
        or not isinstance(handoff, dict) or set(handoff) != HANDOFF_FIELDS
        or checkout.get("schema") != CHECKOUT_SCHEMA
        or clock.get("schema") != CLOCK_SCHEMA
        or handoff.get("schema") != HANDOFF_SCHEMA
        or any(session.get(field) is not value for field, value in AUTHORITY.items())
        or any(handoff.get(field) is not value for field, value in AUTHORITY.items())
        or checkout.get("clean") is not True
        or checkout.get("submodules_clean") is not True
        or checkout.get("object_replacement_disabled") is not True
        or clock.get("confirmed") is not True
        or clock.get("source") != "OPERATOR_CONFIRMED_UTC"
        or clock.get("operator_id") != "jt"
        or handoff.get("operator_id") != "jt"
        or handoff.get("key_id") != KEY_ID
        or handoff.get("namespace") != DEVELOPMENT_NAMESPACE
        or handoff.get("scope") != "DEVELOPMENT_ONLY"
        or not _hex(checkout.get("commit"), 40)
        or not _hex(checkout.get("tree"), 40)
        or not _hex(session.get("receipt_sha256"), 64)
        or not _hex(handoff.get("packet_sha256"), 64)
        or not _hex(handoff.get("receipt_sha256_without_signature"), 64)
        or not _hex(handoff.get("statement_sha256"), 64)
        or not isinstance(clock.get("observed_at"), str)
        or not clock["observed_at"]
        or not isinstance(handoff.get("public_key_fingerprint"), str)
        or not handoff["public_key_fingerprint"]
    ):
        raise ValueError("IndependentAuditSessionInvalid")
    return session


def _review(session: dict[str, Any]) -> bytes:
    checkout = session["checkout_witness"]
    clock = session["clock_witness"]
    handoff = session["handoff"]
    lines = [
        "AEGIS DEVELOPMENT-ONLY SIGNING REVIEW", "", "SIGNED OBJECT",
        f"  Commit: {checkout['commit']}", f"  Tree: {checkout['tree']}",
        f"  Operator-confirmed UTC: {clock['observed_at']}",
        f"  Public-key fingerprint: {handoff['public_key_fingerprint']}",
        f"  Receipt SHA-256: {session['receipt_sha256']}",
        f"  Namespace: {SESSION_NAMESPACE}", "", "AUTHORITY",
        "  Scope: DEVELOPMENT_ONLY", "  Production authority: NO",
        "  Deployment authority: NO", "  Hardware authority: NO",
        "  Storage-write authority: NO", "  Automatic promotion: NO", "",
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
        f"   ssh-keygen -Y sign -f <JT_PRIVATE_KEY> -n {SESSION_NAMESPACE} "
        "aegis-development-signing-session.json\n\n"
        "5. Return only aegis-development-signing-session.json.sig.\n"
        "Never copy the private key into this directory, TruePanel, or BattleStation.\n"
        "This signature cannot authorize production, deployment, storage, network, or hardware action.\n"
    ).encode()


def audit(directory_value: str | Path) -> dict[str, Any]:
    directory = Path(directory_value)
    if (
        not directory.is_absolute() or directory.is_symlink()
        or directory.resolve(strict=True) != directory or not directory.is_dir()
    ):
        raise ValueError("IndependentAuditLayoutInvalid")
    with os.scandir(directory) as entries:
        if {entry.name for entry in entries} != KIT_FILES:
            raise ValueError("IndependentAuditLayoutInvalid")
    statement = _read_regular(directory / "aegis-development-signing-session.json")
    review = _read_regular(directory / "aegis-development-review.txt")
    instructions = _read_regular(directory / "README.txt")
    manifest_bytes = _read_regular(directory / "manifest.json")
    session = _validate_session(_json(statement))
    manifest = _json(manifest_bytes)
    if statement != _canonical(session):
        raise ValueError("IndependentAuditSessionNotCanonical")
    if not isinstance(manifest, dict) or set(manifest) != MANIFEST_FIELDS:
        raise ValueError("IndependentAuditManifestInvalid")
    expected_review = _review(session)
    expected_instructions = _instructions()
    expected_manifest = {
        "schema": MANIFEST_SCHEMA,
        "session_file": "aegis-development-signing-session.json",
        "session_sha256": _sha256(statement),
        "review_file": "aegis-development-review.txt",
        "review_sha256": _sha256(expected_review),
        "instructions_file": "README.txt",
        "instructions_sha256": _sha256(expected_instructions),
        "signature_file": "aegis-development-signing-session.json.sig",
        "namespace": SESSION_NAMESPACE, "key_id": KEY_ID,
        "scope": "DEVELOPMENT_ONLY", **AUTHORITY,
    }
    if (
        review != expected_review or instructions != expected_instructions
        or manifest != expected_manifest or manifest_bytes != _canonical(expected_manifest)
    ):
        raise ValueError("IndependentAuditPresentationMismatch")
    return {
        "schema": WITNESS_SCHEMA, "status": "INDEPENDENT_AUDIT_PASS",
        "session_sha256": expected_manifest["session_sha256"],
        "review_sha256": expected_manifest["review_sha256"],
        "manifest_sha256": _sha256(manifest_bytes), "scope": "DEVELOPMENT_ONLY",
        **AUTHORITY,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Independently audit an AEGIS signing kit")
    parser.add_argument("kit", type=Path)
    arguments = parser.parse_args()
    try:
        result = audit(arguments.kit)
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "HOLD", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
