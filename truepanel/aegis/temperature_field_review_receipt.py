"""Content-bound offline review receipt for one temperature recording."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

from .ssh_verifier import (
    MAX_ALLOWED_SIGNERS_BYTES,
    validate_allowed_signers_roster,
)
from .temperature_authenticated_acceptance import (
    KEY_ID,
)
from .temperature_authenticated_acceptance import (
    NAMESPACE as DEVELOPMENT_NAMESPACE,
)
from .temperature_field_checkride import STATUS_FIELD_REVIEW
from .temperature_recording_intake import evaluate_temperature_recording_intake

SCHEMA: Final = "truepanel.aegis-temperature-field-review/v1"
STATEMENT_SCHEMA: Final = "truepanel.aegis-temperature-field-review-statement/v1"
KIT_SCHEMA: Final = "truepanel.aegis-temperature-field-review-kit/v1"
NAMESPACE: Final = "truepanel-aegis-temperature-field-review-v1@truepanel"
SCOPE: Final = "temperature-field-observation-calibration-review-only"
STATUS_READY: Final = "READY_FOR_OFFLINE_FIELD_REVIEW_SIGNATURE"
STATUS_SIGNATURE_REQUIRED: Final = "ACTION_REQUIRED_FIELD_REVIEW_SIGNATURE"
STATUS_HOLD: Final = "HOLD"
MAX_PUBLIC_FILE_BYTES: Final = 128 * 1024
MAX_SIGNATURE_BYTES: Final = 32 * 1024
MAX_REVIEW_WINDOW: Final = timedelta(hours=2)
_FILES: Final = (
    "field-review-statement.json",
    "manifest.json",
    "FIELD_REVIEW_SIGNING.txt",
)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _record_sha256(value: Any) -> str:
    return _sha256(_canonical(value))


def _utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("FieldReviewTimeInvalid")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo != UTC:
        raise ValueError("FieldReviewTimeInvalid")
    return parsed


def _validate_window(*, prepared_at_utc: str, expires_at_utc: str, now_utc: str) -> None:
    prepared = _utc(prepared_at_utc)
    expires = _utc(expires_at_utc)
    now = _utc(now_utc)
    if expires <= prepared or expires - prepared > MAX_REVIEW_WINDOW:
        raise ValueError("FieldReviewWindowInvalid")
    if now < prepared or now >= expires:
        raise ValueError("FieldReviewStatementExpiredOrNotYetValid")


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _write_new(path: Path, payload: bytes) -> None:
    if not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("NoFollowUnavailable")
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("FieldReviewKitWriteFailed")
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
            chunk = os.read(descriptor, min(65_536, remaining))
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
        "AEGIS TEMPERATURE FIELD OBSERVATION REVIEW - PUBLIC SIGNING KIT\n"
        f"Statement SHA-256: {statement_sha256}\n"
        f"SSHSIG namespace: {NAMESPACE}\n"
        f"Signer identity: {KEY_ID}\n"
        "Review the exact sanitized recording named by digest in statement.json.\n"
        "Sign only after confirming opt-in and reviewing the incident outcome.\n"
        "Keep the private key outside TruePanel and return only the SSHSIG.\n"
        "This signature permits calibration review only; it grants no validation, "
        "installation, deployment, storage, network, or hardware authority.\n"
    ).encode("ascii")


def _operator_key_fingerprint(verifier: Any, *, namespace: str) -> str:
    """Pin one exact protected roster and namespace, not merely a principal."""

    if (
        getattr(verifier, "namespace", None) != namespace
        or getattr(verifier, "expected_key_ids", None) != (KEY_ID,)
    ):
        raise ValueError("FieldReviewVerifierPolicyMismatch")
    roster_path = getattr(verifier, "allowed_signers_path", None)
    if not isinstance(roster_path, Path):
        raise ValueError("FieldReviewVerifierPolicyMismatch")
    roster = validate_allowed_signers_roster(
        _snapshot(roster_path, MAX_ALLOWED_SIGNERS_BYTES),
        expected_key_ids=(KEY_ID,),
    )
    return roster[KEY_ID]


def _validate_review_trust_root(
    development_verifier: Any,
    review_verifier: Any,
    expected_fingerprint: str,
) -> None:
    development_fingerprint = _operator_key_fingerprint(
        development_verifier, namespace=DEVELOPMENT_NAMESPACE
    )
    review_fingerprint = _operator_key_fingerprint(review_verifier, namespace=NAMESPACE)
    development_roster = development_verifier.allowed_signers_path.resolve(strict=True)
    review_roster = review_verifier.allowed_signers_path.resolve(strict=True)
    if (
        development_roster != review_roster
        or development_fingerprint != review_fingerprint
        or review_fingerprint != expected_fingerprint
    ):
        raise ValueError("FieldReviewTrustRootMismatch")


def build_temperature_field_review_statement(
    candidate: dict[str, Any],
    appraisal: dict[str, Any],
    confirmation: dict[str, Any],
    development_kit_directory: str | Path,
    development_signature_path: str | Path,
    development_verifier: Any,
    recording_path: str | Path,
    *,
    prepared_at_utc: str,
    expires_at_utc: str,
    now_utc: str,
) -> bytes:
    """Reconstruct the exact field-review statement JT signs offline."""

    _validate_window(
        prepared_at_utc=prepared_at_utc,
        expires_at_utc=expires_at_utc,
        now_utc=now_utc,
    )
    operator_key_fingerprint = _operator_key_fingerprint(
        development_verifier, namespace=DEVELOPMENT_NAMESPACE
    )
    intake = evaluate_temperature_recording_intake(
        candidate,
        appraisal,
        confirmation,
        str(development_kit_directory),
        str(development_signature_path),
        development_verifier,
        recording_path,
        # The signed subject must be stable throughout the review window.
        # Current time is checked above; the underlying evidence is rebuilt at
        # the statement's preparation instant so later verification produces
        # byte-identical content.
        now_utc=prepared_at_utc,
        evidence_source="holodeck-deterministic",
    )
    if intake.get("status") != "SIMULATION_REHEARSAL_PASSED":
        raise ValueError("FieldReviewRecordingNotAcceptable")
    statement = {
        "schema": STATEMENT_SCHEMA,
        "namespace": NAMESPACE,
        "key_id": KEY_ID,
        "operator_key_fingerprint": operator_key_fingerprint,
        "scope": SCOPE,
        "prepared_at_utc": prepared_at_utc,
        "expires_at_utc": expires_at_utc,
        "development_authentication_record_sha256": intake.get(
            "development_authentication_record_sha256"
        ),
        "intake_record_sha256": intake["record_sha256"],
        "recording_sha256": intake["recording_sha256"],
        "recording_bytes": intake["recording_bytes"],
        "frame_count": intake["frame_count"],
        "observation_source": "operator-opt-in-field",
        "operator_statement": (
            "I opt in this exact sanitized recording for calibration review and "
            "confirm that I reviewed the incident outcome."
        ),
        "operator_opt_in": True,
        "privacy_sanitized_reviewed": True,
        "incident_outcome_reviewed": True,
        "field_validated": False,
        "production_validated": False,
        "candidate_accepted": False,
        "candidate_installed": False,
        "runtime_authority": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "storage_write_authority": False,
        "network_authority": False,
        "automatic_promotion": False,
    }
    return _canonical(statement)


def _manifest(statement: bytes) -> dict[str, Any]:
    instructions = _instructions(_sha256(statement))
    return {
        "schema": KIT_SCHEMA,
        "key_id": KEY_ID,
        "namespace": NAMESPACE,
        "scope": SCOPE,
        "statement_sha256": _sha256(statement),
        "instructions_sha256": _sha256(instructions),
        "file_count": len(_FILES),
        "private_key_expected": False,
        "field_validated": False,
        "candidate_installed": False,
        "deployment_authority": False,
        "hardware_authority": False,
    }


def export_temperature_field_review_kit(
    candidate: dict[str, Any],
    appraisal: dict[str, Any],
    confirmation: dict[str, Any],
    development_kit_directory: str | Path,
    development_signature_path: str | Path,
    development_verifier: Any,
    recording_path: str | Path,
    output_directory: str | Path,
    *,
    source_root: str | Path,
    prepared_at_utc: str,
    expires_at_utc: str,
    now_utc: str,
) -> dict[str, Any]:
    """Export only public review material outside the source checkout."""

    output = Path(output_directory)
    source = Path(source_root)
    errors: list[str] = []
    created = False
    statement = b""
    try:
        if not output.is_absolute() or not source.is_absolute():
            raise ValueError("AbsolutePathsRequired")
        if source.is_symlink():
            raise ValueError("SourceCheckoutSymlinkInvalid")
        resolved_source = source.resolve(strict=True)
        projected = output.parent.resolve(strict=True) / output.name
        if output.is_symlink() or _inside(projected, resolved_source):
            raise ValueError("FieldReviewKitMustBeOutsideSourceCheckout")
        if output.exists():
            raise ValueError("FieldReviewKitOutputAlreadyExists")
        statement = build_temperature_field_review_statement(
            candidate,
            appraisal,
            confirmation,
            development_kit_directory,
            development_signature_path,
            development_verifier,
            recording_path,
            prepared_at_utc=prepared_at_utc,
            expires_at_utc=expires_at_utc,
            now_utc=now_utc,
        )
        manifest = _manifest(statement)
        output.mkdir(mode=0o700)
        created = True
        _write_new(output / _FILES[0], statement)
        _write_new(output / _FILES[1], _canonical(manifest) + b"\n")
        _write_new(output / _FILES[2], _instructions(_sha256(statement)))
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
        "schema": SCHEMA,
        "status": STATUS_READY if ready else STATUS_HOLD,
        "review_kit_created": ready,
        "review_statement_sha256": _sha256(statement) if statement else None,
        "file_count": len(_FILES) if ready else 0,
        "errors": errors,
        "private_key_accepted": False,
        "signer_invoked": False,
        "field_validated": False,
        "candidate_accepted": False,
        "candidate_installed": False,
        "deployment_authority": False,
        "hardware_authority": False,
    }
    result["record_sha256"] = _record_sha256(result)
    return result


def evaluate_temperature_field_review_receipt(
    candidate: dict[str, Any],
    appraisal: dict[str, Any],
    confirmation: dict[str, Any],
    development_kit_directory: str | Path,
    development_signature_path: str | Path,
    development_verifier: Any,
    recording_path: str | Path,
    review_kit_directory: str | Path,
    review_signature_path: str | Path | None,
    review_verifier: Any,
    *,
    prepared_at_utc: str,
    expires_at_utc: str,
    now_utc: str,
) -> dict[str, Any]:
    """Verify JT's content-bound review receipt, then replay the field intake."""

    errors: list[str] = []
    statement = b""
    statement_data: dict[str, Any] = {}
    signature_verified = False
    final_intake: dict[str, Any] = {}
    try:
        statement = build_temperature_field_review_statement(
            candidate,
            appraisal,
            confirmation,
            development_kit_directory,
            development_signature_path,
            development_verifier,
            recording_path,
            prepared_at_utc=prepared_at_utc,
            expires_at_utc=expires_at_utc,
            now_utc=now_utc,
        )
        statement_data = json.loads(statement)
        review_kit = Path(review_kit_directory)
        if not review_kit.is_absolute() or review_kit.is_symlink():
            raise ValueError("ProtectedFieldReviewKitUnavailable")
        if {item.name for item in review_kit.iterdir()} != set(_FILES):
            raise ValueError("FieldReviewKitFileSetInvalid")
        if _snapshot(review_kit / _FILES[0], MAX_PUBLIC_FILE_BYTES) != statement:
            raise ValueError("FieldReviewStatementMismatch")
        if _snapshot(review_kit / _FILES[1], MAX_PUBLIC_FILE_BYTES) != (
            _canonical(_manifest(statement)) + b"\n"
        ):
            raise ValueError("FieldReviewManifestMismatch")
        if _snapshot(review_kit / _FILES[2], MAX_PUBLIC_FILE_BYTES) != _instructions(
            _sha256(statement)
        ):
            raise ValueError("FieldReviewInstructionsMismatch")
        if review_signature_path is None:
            raise ValueError("FieldReviewSignatureRequired")
        _validate_review_trust_root(
            development_verifier,
            review_verifier,
            statement_data.get("operator_key_fingerprint"),
        )
        review_signature = _snapshot(
            Path(review_signature_path), MAX_SIGNATURE_BYTES
        ).decode("ascii")
        signature_verified = (
            review_verifier(KEY_ID, statement, review_signature) is True
        )
        if not signature_verified:
            raise ValueError("FieldReviewSignatureNotAuthenticated")
        final_intake = evaluate_temperature_recording_intake(
            candidate,
            appraisal,
            confirmation,
            str(development_kit_directory),
            str(development_signature_path),
            development_verifier,
            recording_path,
            now_utc=prepared_at_utc,
            evidence_source="operator-opt-in-field",
            operator_opt_in=True,
            incident_reviewed=True,
        )
        if final_intake.get("status") != STATUS_FIELD_REVIEW:
            raise ValueError("FieldReviewReplayNotAcceptable")
        if (
            final_intake.get("recording_sha256")
            != statement_data.get("recording_sha256")
            or final_intake.get("recording_bytes")
            != statement_data.get("recording_bytes")
            or final_intake.get("development_authentication_record_sha256")
            != statement_data.get("development_authentication_record_sha256")
        ):
            raise ValueError("FieldReviewSubjectChanged")
    except (
        FileNotFoundError,
        NotADirectoryError,
        OSError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
    ) as error:
        errors.append(str(error) or error.__class__.__name__)

    accepted = not errors and signature_verified
    result = {
        "schema": SCHEMA,
        "status": STATUS_FIELD_REVIEW if accepted else STATUS_HOLD,
        "operator_id": "jt",
        "key_id": KEY_ID,
        "namespace": NAMESPACE,
        "scope": SCOPE,
        "development_signature_verified": final_intake.get(
            "operator_signature_verified"
        )
        is True,
        "operator_review_signature_verified": signature_verified,
        "review_statement_sha256": _sha256(statement) if statement else None,
        "recording_sha256": statement_data.get("recording_sha256"),
        "recording_bytes": statement_data.get("recording_bytes", 0),
        "frame_count": statement_data.get("frame_count", 0),
        "operator_opt_in": accepted,
        "privacy_sanitized_reviewed": accepted,
        "incident_outcome_reviewed": accepted,
        "eligible_for_calibration_review": accepted,
        "field_validated": False,
        "production_validated": False,
        "candidate_accepted": False,
        "candidate_installed": False,
        "runtime_authority": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "storage_write_authority": False,
        "network_authority": False,
        "automatic_promotion": False,
        "private_key_accepted": False,
        "signer_invoked": False,
        "errors": errors,
    }
    result["record_sha256"] = _record_sha256(result)
    return result


def pending_temperature_field_review_receipt(
    recording_intake: dict[str, Any],
) -> dict[str, Any]:
    """Expose the honest live state before recording and review signatures exist."""

    development_verified = (
        recording_intake.get("operator_signature_verified") is True
    )
    result = {
        "schema": SCHEMA,
        "status": (
            STATUS_SIGNATURE_REQUIRED if development_verified else STATUS_HOLD
        ),
        "development_signature_verified": development_verified,
        "recording_present": recording_intake.get("recording_present") is True,
        "review_kit_created": False,
        "operator_review_signature_verified": False,
        "operator_opt_in": False,
        "privacy_sanitized_reviewed": False,
        "incident_outcome_reviewed": False,
        "eligible_for_calibration_review": False,
        "field_validated": False,
        "production_validated": False,
        "candidate_accepted": False,
        "candidate_installed": False,
        "runtime_authority": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "storage_write_authority": False,
        "network_authority": False,
        "automatic_promotion": False,
        "private_key_accepted": False,
        "signer_invoked": False,
        "next_action": (
            "verify JT's development-only SSHSIG"
            if not development_verified
            else "export and independently review the exact field-review statement"
        ),
        "errors": (
            [] if development_verified else ["authenticated development record required"]
        ),
    }
    result["record_sha256"] = _record_sha256(result)
    return result


__all__ = [
    "NAMESPACE",
    "STATUS_HOLD",
    "STATUS_READY",
    "STATUS_SIGNATURE_REQUIRED",
    "build_temperature_field_review_statement",
    "evaluate_temperature_field_review_receipt",
    "export_temperature_field_review_kit",
    "pending_temperature_field_review_receipt",
]
