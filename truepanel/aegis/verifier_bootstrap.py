"""Fail-closed content pinning for the standalone AEGIS kit auditor.

This verifies a public release receipt and the exact verifier source bytes.  It
does not execute the verifier, establish an out-of-band trust channel, inspect
a signing kit, or grant any signing or production authority.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any

RELEASE_SCHEMA = "truepanel.aegis-independent-verifier-release/v1"
RELEASE_ID = "aegis-independent-kit-auditor-v1"
WITNESS_SCHEMA = "truepanel.aegis-independent-kit-audit-witness/v1"
MAX_BYTES = 1024 * 1024
AUTHORITY = {
    "production_authority": False,
    "deployment_authority": False,
    "hardware_authority": False,
    "storage_write_authority": False,
    "automatic_promotion": False,
}
RELEASE_FIELDS = {
    "schema",
    "release_id",
    "source_repository",
    "source_commit",
    "source_url",
    "verifier_path",
    "source_sha256",
    "source_git_blob_sha1",
    "source_size_bytes",
    "python_requires",
    "invocation",
    "witness_schema",
    "scope",
    "network_required",
    "truepanel_imports",
    "private_key_inputs",
    "signer_invocations",
    "independent_channel_required",
    *AUTHORITY,
}
ALLOWED_IMPORTS = {
    "__future__",
    "argparse",
    "hashlib",
    "json",
    "os",
    "pathlib",
    "stat",
    "sys",
    "typing",
}


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("VerifierBootstrapDuplicateJsonKey")
        result[key] = value
    return result


def _read_regular(path: Path) -> bytes:
    if not path.is_absolute() or path.is_symlink() or not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("VerifierBootstrapUnsafePath")
    try:
        if path.resolve(strict=True) != path:
            raise ValueError("VerifierBootstrapUnsafePath")
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_BYTES:
                raise ValueError("VerifierBootstrapInvalidFile")
            content = b""
            while len(content) <= MAX_BYTES:
                chunk = os.read(descriptor, min(65536, MAX_BYTES + 1 - len(content)))
                if not chunk:
                    break
                content += chunk
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
            if len(content) > MAX_BYTES or identity(before) != identity(after):
                raise ValueError("VerifierBootstrapChangingFile")
            return content
        finally:
            os.close(descriptor)
    except OSError as error:
        raise ValueError("VerifierBootstrapUnavailableFile") from error


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _hex(value: Any, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value)
    )


def _git_blob_sha1(content: bytes) -> str:
    header = f"blob {len(content)}\0".encode()
    return hashlib.sha1(header + content, usedforsecurity=False).hexdigest()


def _validate_source_policy(content: bytes) -> None:
    try:
        source = content.decode("utf-8")
        tree = ast.parse(source)
    except (UnicodeDecodeError, SyntaxError) as error:
        raise ValueError("VerifierBootstrapInvalidPython") from error
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level or node.module is None:
                raise ValueError("VerifierBootstrapUnsafeImport")
            imports.add(node.module.split(".", 1)[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
            if any("private" in item.arg.lower() for item in arguments):
                raise ValueError("VerifierBootstrapPrivateKeyInput")
    if not imports <= ALLOWED_IMPORTS or "truepanel" in imports:
        raise ValueError("VerifierBootstrapUnsafeImport")


def verify_verifier_release(
    *, receipt_path: str | Path, source_path: str | Path
) -> dict[str, Any]:
    """Verify exact source identity and static safety properties without execution."""

    receipt_bytes = _read_regular(Path(receipt_path))
    source_bytes = _read_regular(Path(source_path))
    try:
        receipt = json.loads(receipt_bytes, object_pairs_hook=_no_duplicates)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("VerifierBootstrapInvalidReceipt") from error
    if not isinstance(receipt, dict) or set(receipt) != RELEASE_FIELDS:
        raise ValueError("VerifierBootstrapInvalidReceipt")
    if receipt_bytes != _canonical(receipt) + b"\n":
        raise ValueError("VerifierBootstrapReceiptNotCanonical")
    expected_url = (
        "https://raw.githubusercontent.com/johnnyvontruant/TruePanel/"
        f"{receipt.get('source_commit')}/"
        "truepanel/holodeck/aegis_independent_kit_auditor.py"
    )
    if (
        receipt.get("schema") != RELEASE_SCHEMA
        or receipt.get("release_id") != RELEASE_ID
        or receipt.get("source_repository") != "johnnyvontruant/TruePanel"
        or receipt.get("verifier_path")
        != "truepanel/holodeck/aegis_independent_kit_auditor.py"
        or receipt.get("python_requires") != ">=3.11"
        or receipt.get("witness_schema") != WITNESS_SCHEMA
        or receipt.get("scope") != "DEVELOPMENT_ONLY"
        or receipt.get("network_required") is not False
        or receipt.get("truepanel_imports") != 0
        or receipt.get("private_key_inputs") != 0
        or receipt.get("signer_invocations") != 0
        or receipt.get("independent_channel_required") is not True
        or any(receipt.get(field) is not value for field, value in AUTHORITY.items())
        or not _hex(receipt.get("source_commit"), 40)
        or not _hex(receipt.get("source_sha256"), 64)
        or not _hex(receipt.get("source_git_blob_sha1"), 40)
        or not isinstance(receipt.get("source_size_bytes"), int)
        or receipt["source_size_bytes"] <= 0
        or receipt.get("source_url") != expected_url
        or receipt.get("invocation")
        != "python -I aegis_independent_kit_auditor.py <absolute-kit-path>"
    ):
        raise ValueError("VerifierBootstrapPolicyMismatch")
    if (
        len(source_bytes) != receipt["source_size_bytes"]
        or hashlib.sha256(source_bytes).hexdigest() != receipt["source_sha256"]
        or _git_blob_sha1(source_bytes) != receipt["source_git_blob_sha1"]
    ):
        raise ValueError("VerifierBootstrapSourceMismatch")
    _validate_source_policy(source_bytes)
    return {
        "schema": "truepanel.aegis-independent-verifier-bootstrap-result/v1",
        "status": "VERIFIER_CONTENT_PIN_VERIFIED",
        "release_id": RELEASE_ID,
        "source_commit": receipt["source_commit"],
        "source_sha256": receipt["source_sha256"],
        "source_git_blob_sha1": receipt["source_git_blob_sha1"],
        "independent_channel_verified": False,
        "next_gate": "OPERATOR_OBTAINS_PIN_THROUGH_INDEPENDENT_CHANNEL",
        "scope": "DEVELOPMENT_ONLY",
        **AUTHORITY,
    }


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pin the standalone AEGIS verifier")
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--source", required=True)
    values = parser.parse_args(arguments)
    try:
        result = verify_verifier_release(
            receipt_path=Path(values.receipt), source_path=Path(values.source)
        )
    except ValueError as error:
        print(json.dumps({"status": "HOLD", "reason": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["verify_verifier_release"]
