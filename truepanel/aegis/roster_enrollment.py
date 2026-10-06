"""Public-only enrollment for JT's development-review verification identity.

This module never generates a key, accepts a private key, signs data, or grants
production authority.  It converts one operator-confirmed Ed25519 public key
into the deliberately narrow OpenSSH allowed-signers profile used by AEGIS.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path
from typing import Any

from .operator_handoff import OPERATOR_KEY_ID
from .ssh_verifier import validate_allowed_signers_roster

ENROLLMENT_SCHEMA = "truepanel.aegis-development-public-roster-enrollment/v1"
ENROLLMENT_CONFIRMATION = "ENROLL_JT_DEVELOPMENT_REVIEW_PUBLIC_KEY"
MAX_PUBLIC_KEY_BYTES = 16 * 1024
MAX_ENROLLMENT_RECEIPT_BYTES = 64 * 1024
AUTHORITY = {
    "production_authority": False,
    "deployment_authority": False,
    "hardware_authority": False,
    "storage_write_authority": False,
    "automatic_promotion": False,
}


def _read_snapshot(descriptor: int, *, maximum: int) -> bytes:
    before = os.fstat(descriptor)
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_uid != os.geteuid()
        or before.st_mode & 0o022
        or before.st_size <= 0
        or before.st_size > maximum
    ):
        raise ValueError("PublicKeyFileUnsafe")
    content = b""
    while len(content) <= maximum:
        chunk = os.read(descriptor, min(65536, maximum + 1 - len(content)))
        if not chunk:
            break
        content += chunk
    after = os.fstat(descriptor)

    def identity(value: os.stat_result) -> tuple[int, ...]:
        return (
            value.st_dev,
            value.st_ino,
            value.st_mode,
            value.st_uid,
            value.st_size,
            value.st_mtime_ns,
            value.st_ctime_ns,
        )

    if len(content) > maximum or identity(before) != identity(after):
        raise ValueError("PublicKeyFileChanged")
    return content


def _snapshot(path: Path, *, maximum: int) -> bytes:
    if not path.is_absolute() or path.is_symlink() or not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("PublicKeyPathUnsafe")
    try:
        if path.resolve(strict=True) != path:
            raise ValueError("PublicKeyPathUnsafe")
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            return _read_snapshot(descriptor, maximum=maximum)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise ValueError("PublicKeyUnavailable") from error


def _roster_payload(public_key: bytes) -> tuple[bytes, str]:
    if b"PRIVATE KEY" in public_key:
        raise ValueError("PrivateKeyInputDenied")
    try:
        text = public_key.decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError("PublicKeyEncodingInvalid") from error
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) != 1:
        raise ValueError("PublicKeyCountInvalid")
    fields = lines[0].split()
    # OpenSSH permits a free-form comment after the key blob.  It is not part
    # of the identity, so discard it rather than limiting comments to one word.
    if len(fields) < 2 or fields[0] != "ssh-ed25519":
        raise ValueError("PublicKeyProfileInvalid")
    roster = f"{OPERATOR_KEY_ID} {fields[0]} {fields[1]}\n".encode("ascii")
    inspected = validate_allowed_signers_roster(
        roster, expected_key_ids=(OPERATOR_KEY_ID,)
    )
    return roster, inspected[OPERATOR_KEY_ID]


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode() + b"\n"


def _receipt_path_safe(path: Path, *, checkout: Path) -> bool:
    try:
        parent = path.parent.resolve(strict=True)
        parent_stat = parent.stat()
        return (
            path.is_absolute()
            and path.name not in {"", ".", ".."}
            and not path.is_symlink()
            and not path.exists()
            and parent == path.parent
            and parent.is_dir()
            and parent_stat.st_uid == os.geteuid()
            and not parent_stat.st_mode & 0o022
            and not _is_within(path, checkout)
        )
    except OSError:
        return False


def _write_exclusive(path: Path, content: bytes) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    try:
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short receipt write")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def provision_development_roster(
    *,
    public_key_path: str | Path,
    destination_path: str | Path,
    checkout_root: str | Path,
    expected_fingerprint: str,
    operator_confirmation: str,
    receipt_path: str | Path | None = None,
) -> dict[str, Any]:
    """Create one protected public roster outside the source checkout."""

    if operator_confirmation != ENROLLMENT_CONFIRMATION:
        raise ValueError("RosterEnrollmentConfirmationRequired")
    checkout = Path(checkout_root)
    destination = Path(destination_path)
    try:
        if (
            not checkout.is_absolute()
            or checkout.is_symlink()
            or checkout.resolve(strict=True) != checkout
            or not checkout.is_dir()
            or not destination.is_absolute()
            or destination.name in {"", ".", ".."}
            or destination.is_symlink()
            or destination.exists()
        ):
            raise ValueError("RosterEnrollmentPathUnsafe")
        parent = destination.parent.resolve(strict=True)
        parent_stat = parent.stat()
        if (
            parent != destination.parent
            or not parent.is_dir()
            or parent_stat.st_uid != os.geteuid()
            or parent_stat.st_mode & 0o022
            or _is_within(destination, checkout)
        ):
            raise ValueError("RosterEnrollmentPathUnsafe")
    except OSError as error:
        raise ValueError("RosterEnrollmentPathUnsafe") from error

    public_key = _snapshot(Path(public_key_path), maximum=MAX_PUBLIC_KEY_BYTES)
    roster, fingerprint = _roster_payload(public_key)
    if not expected_fingerprint or fingerprint != expected_fingerprint:
        raise ValueError("PublicKeyFingerprintMismatch")

    descriptor: int | None = None
    parent_descriptor: int | None = None
    created = False
    try:
        parent_descriptor = os.open(
            parent,
            os.O_RDONLY
            | os.O_CLOEXEC
            | os.O_NOFOLLOW
            | getattr(os, "O_DIRECTORY", 0),
        )
        opened_parent = os.fstat(parent_descriptor)
        if (
            opened_parent.st_dev != parent_stat.st_dev
            or opened_parent.st_ino != parent_stat.st_ino
            or opened_parent.st_uid != os.geteuid()
            or opened_parent.st_mode & 0o022
        ):
            raise ValueError("RosterEnrollmentPathUnsafe")
        descriptor = os.open(
            destination.name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
            dir_fd=parent_descriptor,
        )
        created = True
        view = memoryview(roster)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short roster write")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.fsync(parent_descriptor)
        installed_descriptor = os.open(
            destination.name,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
            dir_fd=parent_descriptor,
        )
        try:
            installed = _read_snapshot(
                installed_descriptor, maximum=MAX_PUBLIC_KEY_BYTES
            )
        finally:
            os.close(installed_descriptor)
        inspected = validate_allowed_signers_roster(
            installed, expected_key_ids=(OPERATOR_KEY_ID,)
        )
        if installed != roster or inspected[OPERATOR_KEY_ID] != fingerprint:
            raise ValueError("RosterEnrollmentVerificationFailed")
    except (OSError, ValueError):
        if descriptor is not None:
            os.close(descriptor)
        if created:
            with suppress(OSError):
                os.unlink(destination.name, dir_fd=parent_descriptor)
        raise ValueError("RosterEnrollmentFailed") from None
    finally:
        if parent_descriptor is not None:
            os.close(parent_descriptor)

    result = {
        "schema": ENROLLMENT_SCHEMA,
        "status": "PUBLIC_ROSTER_PROVISIONED_FOR_DEVELOPMENT_REVIEW",
        "operator_id": "jt",
        "key_id": OPERATOR_KEY_ID,
        "public_key_fingerprint": fingerprint,
        "roster_sha256": hashlib.sha256(roster).hexdigest(),
        "roster_path": str(destination),
        "scope": "DEVELOPMENT_ONLY",
        "private_key_accepted": False,
        "signer_invoked": False,
        "next_gate": "BUILD_CONTENT_BOUND_SIGNING_SESSION",
        **AUTHORITY,
    }
    if receipt_path is not None:
        receipt = Path(receipt_path)
        if not _receipt_path_safe(receipt, checkout=checkout):
            with suppress(OSError):
                destination.unlink()
            raise ValueError("RosterEnrollmentReceiptPathUnsafe")
        try:
            _write_exclusive(receipt, _canonical(result))
            audit_development_roster_enrollment(
                receipt_path=receipt,
                allowed_signers_path=destination,
                operator_confirmed_fingerprint=fingerprint,
            )
        except (OSError, ValueError) as error:
            with suppress(OSError):
                destination.unlink()
            with suppress(OSError):
                receipt.unlink()
            raise ValueError("RosterEnrollmentReceiptWriteFailed") from error
    return result


def audit_development_roster_enrollment(
    *,
    receipt_path: str | Path,
    allowed_signers_path: str | Path,
    operator_confirmed_fingerprint: str,
) -> dict[str, Any]:
    """Reconstruct one public roster enrollment at its final consumer.

    The fingerprint remains operator-confirmed public input.  This unsigned
    receipt records and binds that ceremony; it does not authenticate JT.
    """

    roster_path = Path(allowed_signers_path)
    roster = _snapshot(roster_path, maximum=MAX_PUBLIC_KEY_BYTES)
    fingerprints = validate_allowed_signers_roster(
        roster, expected_key_ids=(OPERATOR_KEY_ID,)
    )
    fingerprint = fingerprints[OPERATOR_KEY_ID]
    if not operator_confirmed_fingerprint or fingerprint != operator_confirmed_fingerprint:
        raise ValueError("RosterEnrollmentFingerprintMismatch")
    receipt_bytes = _snapshot(
        Path(receipt_path), maximum=MAX_ENROLLMENT_RECEIPT_BYTES
    )
    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("RosterEnrollmentReceiptDuplicateJsonKey")
            value[key] = item
        return value

    try:
        receipt = json.loads(receipt_bytes, object_pairs_hook=no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("RosterEnrollmentReceiptInvalid") from error
    expected = {
        "schema": ENROLLMENT_SCHEMA,
        "status": "PUBLIC_ROSTER_PROVISIONED_FOR_DEVELOPMENT_REVIEW",
        "operator_id": "jt",
        "key_id": OPERATOR_KEY_ID,
        "public_key_fingerprint": fingerprint,
        "roster_sha256": hashlib.sha256(roster).hexdigest(),
        "roster_path": str(roster_path),
        "scope": "DEVELOPMENT_ONLY",
        "private_key_accepted": False,
        "signer_invoked": False,
        "next_gate": "BUILD_CONTENT_BOUND_SIGNING_SESSION",
        **AUTHORITY,
    }
    if not isinstance(receipt, dict) or receipt != expected or receipt_bytes != _canonical(receipt):
        raise ValueError("RosterEnrollmentReceiptMismatch")
    return {
        "schema": "truepanel.aegis-development-public-roster-enrollment-audit/v1",
        "status": "PUBLIC_ROSTER_ENROLLMENT_VERIFIED",
        "operator_id": "jt",
        "key_id": OPERATOR_KEY_ID,
        "public_key_fingerprint": fingerprint,
        "roster_sha256": expected["roster_sha256"],
        "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        "operator_identity_cryptographically_verified": False,
        "scope": "DEVELOPMENT_ONLY",
        "private_key_accepted": False,
        "signer_invoked": False,
        **AUTHORITY,
    }


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Enroll JT's public development-review identity"
    )
    parser.add_argument("--public-key", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--checkout", required=True, type=Path)
    parser.add_argument("--expected-fingerprint", required=True)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--receipt", required=True, type=Path)
    values = parser.parse_args(arguments)
    try:
        result = provision_development_roster(
            public_key_path=values.public_key,
            destination_path=values.destination,
            checkout_root=values.checkout,
            expected_fingerprint=values.expected_fingerprint,
            operator_confirmation=values.confirm,
            receipt_path=values.receipt,
        )
    except ValueError as error:
        print(json.dumps({"status": "HOLD", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ENROLLMENT_CONFIRMATION",
    "ENROLLMENT_SCHEMA",
    "audit_development_roster_enrollment",
    "provision_development_roster",
]
