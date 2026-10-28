"""Operator-authenticated accept-or-hold decision for a reviewed score."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Mapping
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

from .ssh_verifier import (
    MAX_ALLOWED_SIGNERS_BYTES,
    MAX_SIGNATURE_BYTES,
    validate_allowed_signers_roster,
)
from .temperature_authenticated_acceptance import KEY_ID
from .temperature_score_review import (
    RECEIPT_SCHEMA as REVIEW_RECEIPT_SCHEMA,
)
from .temperature_score_review import (
    STATUS_REVIEWED,
)

SCHEMA: Final = "truepanel.aegis-temperature-calibration-decision/v1"
STATEMENT_SCHEMA: Final = (
    "truepanel.aegis-temperature-calibration-decision-statement/v1"
)
RECEIPT_SCHEMA: Final = "truepanel.aegis-temperature-calibration-decision-receipt/v1"
NAMESPACE: Final = "truepanel-aegis-temperature-calibration-decision-v1@truepanel"
SCOPE: Final = "temperature-calibration-candidate-review-only"
STATUS_READY: Final = "READY_FOR_OFFLINE_CALIBRATION_DECISION_SIGNATURE"
STATUS_ACCEPTED: Final = "ELIGIBLE_FOR_CALIBRATION_CANDIDATE_REVIEW"
STATUS_HELD: Final = "CALIBRATION_CANDIDATE_OPERATOR_HOLD_RECORDED"
STATUS_REQUIRED: Final = "ACTION_REQUIRED_AUTHENTICATED_CALIBRATION_DECISION"
STATUS_HOLD: Final = "HOLD"
DECISION_ACCEPT: Final = "ACCEPT_FOR_CALIBRATION_CANDIDATE_REVIEW"
DECISION_HOLD: Final = "HOLD_CALIBRATION_CANDIDATE"
MAX_WINDOW: Final = timedelta(hours=2)
MAX_PUBLIC_BYTES: Final = 2 * 1024 * 1024

_AUTHORITY_KEYS = {
    "field_validated",
    "production_validated",
    "candidate_installed",
    "runtime_authority",
    "deployment_authority",
    "hardware_authority",
    "storage_write_authority",
    "network_authority",
    "automatic_promotion",
}
_REVIEW_KEYS = {
    "schema",
    "status",
    "reviewed_at_utc",
    "implementation_id",
    "statistical_contract_sha256",
    "blinded_manifest_sha256",
    "detector_contract_sha256",
    "label_statement_sha256",
    "label_signature_sha256",
    "score_receipt_sha256",
    "score_sha256",
    "score",
    "independent_reconstruction_matched",
    "statistical_gates_passed",
    "score_registry_read_only",
    "score_re_evaluated",
    "labels_changed",
    "thresholds_changed",
    "case_exclusions",
    "limitations",
    "review_receipt_sha256",
    "candidate_accepted",
    *_AUTHORITY_KEYS,
}
_STATEMENT_KEYS = {
    "schema",
    "namespace",
    "scope",
    "key_id",
    "operator_key_fingerprint",
    "prepared_at_utc",
    "expires_at_utc",
    "decision",
    "rationale",
    "review_receipt_sha256",
    "score_receipt_sha256",
    "score_sha256",
    "statistical_contract_sha256",
    "blinded_manifest_sha256",
    "detector_contract_sha256",
    "statistical_gates_passed",
    "independent_reconstruction_matched",
    "operator_statement",
    "candidate_review_eligible",
    "candidate_accepted",
    *_AUTHORITY_KEYS,
}
_RECEIPT_KEYS = {
    "schema",
    "status",
    "recorded_at_utc",
    "decision",
    "rationale",
    "decision_statement_sha256",
    "decision_signature_sha256",
    "review_receipt_sha256",
    "score_receipt_sha256",
    "score_sha256",
    "statistical_contract_sha256",
    "blinded_manifest_sha256",
    "detector_contract_sha256",
    "operator_key_fingerprint",
    "statistical_gates_passed",
    "independent_reconstruction_matched",
    "candidate_review_eligible",
    "candidate_accepted",
    "receipt_sha256",
    *_AUTHORITY_KEYS,
}
_RATIONALES = {
    "score-passed-independent-review",
    "operator-caution",
    "insufficient-field-evidence",
    "score-failed-statistical-gates",
}


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else _canonical(value)
    return hashlib.sha256(payload).hexdigest()


def _utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("CalibrationDecisionTimeInvalid")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo != UTC:
        raise ValueError("CalibrationDecisionTimeInvalid")
    return parsed


def _window(prepared_at_utc: str, expires_at_utc: str, now_utc: str) -> None:
    prepared, expires, now = map(_utc, (prepared_at_utc, expires_at_utc, now_utc))
    if expires <= prepared or expires - prepared > MAX_WINDOW:
        raise ValueError("CalibrationDecisionWindowInvalid")
    if now < prepared or now >= expires:
        raise ValueError("CalibrationDecisionExpiredOrNotYetValid")


def _snapshot(path: Path, maximum: int) -> bytes:
    if not path.is_absolute() or not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("ProtectedCalibrationDecisionFileUnavailable")
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_mode & 0o022
            or before.st_size <= 0
            or before.st_size > maximum
        ):
            raise ValueError("ProtectedCalibrationDecisionFileInvalid")
        payload = b""
        while len(payload) <= maximum:
            chunk = os.read(descriptor, min(65_536, maximum + 1 - len(payload)))
            if not chunk:
                break
            payload += chunk
        after = os.fstat(descriptor)

        def identity(item: os.stat_result) -> tuple[int, ...]:
            return (
                item.st_dev,
                item.st_ino,
                item.st_mode,
                item.st_uid,
                item.st_size,
                item.st_mtime_ns,
                item.st_ctime_ns,
            )

        if identity(before) != identity(after) or len(payload) > maximum:
            raise ValueError("ProtectedCalibrationDecisionFileChanged")
        return payload
    finally:
        os.close(descriptor)


def _fingerprint(verifier: Any) -> str:
    if getattr(verifier, "namespace", None) != NAMESPACE or getattr(
        verifier, "expected_key_ids", None
    ) != (KEY_ID,):
        raise ValueError("CalibrationDecisionVerifierPolicyMismatch")
    path = getattr(verifier, "allowed_signers_path", None)
    if not isinstance(path, Path):
        raise ValueError("CalibrationDecisionVerifierPolicyMismatch")
    return validate_allowed_signers_roster(
        _snapshot(path, MAX_ALLOWED_SIGNERS_BYTES), expected_key_ids=(KEY_ID,)
    )[KEY_ID]


def _review(path: Path) -> dict[str, Any]:
    payload = _snapshot(path, MAX_PUBLIC_BYTES)
    value = json.loads(payload)
    if not isinstance(value, dict) or set(value) != _REVIEW_KEYS:
        raise ValueError("CalibrationDecisionReviewFieldsInvalid")
    if payload != _canonical(value) + b"\n":
        raise ValueError("CalibrationDecisionReviewNotCanonical")
    claimed = value["review_receipt_sha256"]
    unsigned = dict(value)
    del unsigned["review_receipt_sha256"]
    if claimed != _sha256(unsigned):
        raise ValueError("CalibrationDecisionReviewDigestMismatch")
    if (
        value["schema"] != REVIEW_RECEIPT_SCHEMA
        or value["status"] != STATUS_REVIEWED
        or value["independent_reconstruction_matched"] is not True
        or value["score_registry_read_only"] is not True
        or value["score_re_evaluated"] is not False
        or value["labels_changed"] is not False
        or value["thresholds_changed"] is not False
        or value["case_exclusions"] != []
        or any(
            value[key] is not False for key in _AUTHORITY_KEYS | {"candidate_accepted"}
        )
    ):
        raise ValueError("CalibrationDecisionReviewPolicyMismatch")
    if value["statistical_gates_passed"] is not value["score"].get(
        "statistical_gates_passed"
    ):
        raise ValueError("CalibrationDecisionReviewVerdictMismatch")
    return value


def _validate_choice(review: Mapping[str, Any], decision: str, rationale: str) -> None:
    if decision not in {DECISION_ACCEPT, DECISION_HOLD} or rationale not in _RATIONALES:
        raise ValueError("CalibrationDecisionChoiceInvalid")
    passed = review["statistical_gates_passed"] is True
    if decision == DECISION_ACCEPT and (
        not passed or rationale != "score-passed-independent-review"
    ):
        raise ValueError("CalibrationDecisionAcceptanceRequiresPassingReview")
    if decision == DECISION_HOLD and rationale == "score-passed-independent-review":
        raise ValueError("CalibrationDecisionHoldRationaleInvalid")
    if not passed and rationale != "score-failed-statistical-gates":
        raise ValueError("CalibrationDecisionFailedScoreMustRemainHeld")


def build_temperature_calibration_decision_statement(
    review_receipt_path: str | Path,
    verifier: Any,
    *,
    decision: str,
    rationale: str,
    prepared_at_utc: str,
    expires_at_utc: str,
    now_utc: str,
) -> bytes:
    """Bind one operator choice to the exact independently reviewed score."""
    _window(prepared_at_utc, expires_at_utc, now_utc)
    review = _review(Path(review_receipt_path))
    fingerprint = _fingerprint(verifier)
    _validate_choice(review, decision, rationale)
    eligible = decision == DECISION_ACCEPT
    statement = {
        "schema": STATEMENT_SCHEMA,
        "namespace": NAMESPACE,
        "scope": SCOPE,
        "key_id": KEY_ID,
        "operator_key_fingerprint": fingerprint,
        "prepared_at_utc": prepared_at_utc,
        "expires_at_utc": expires_at_utc,
        "decision": decision,
        "rationale": rationale,
        "review_receipt_sha256": review["review_receipt_sha256"],
        "score_receipt_sha256": review["score_receipt_sha256"],
        "score_sha256": review["score_sha256"],
        "statistical_contract_sha256": review["statistical_contract_sha256"],
        "blinded_manifest_sha256": review["blinded_manifest_sha256"],
        "detector_contract_sha256": review["detector_contract_sha256"],
        "statistical_gates_passed": review["statistical_gates_passed"],
        "independent_reconstruction_matched": True,
        "operator_statement": "I record this development-only calibration decision over the exact independent review.",
        "candidate_review_eligible": eligible,
        "candidate_accepted": False,
        **{key: False for key in sorted(_AUTHORITY_KEYS)},
    }
    return _canonical(statement)


def export_temperature_calibration_decision_statement(
    review_receipt_path: str | Path,
    verifier: Any,
    output_path: str | Path,
    **kwargs: Any,
) -> dict[str, Any]:
    errors: list[str] = []
    created = False
    statement = b""
    try:
        statement = build_temperature_calibration_decision_statement(
            review_receipt_path, verifier, **kwargs
        )
        destination = Path(output_path)
        if not destination.is_absolute() or destination.exists():
            raise ValueError("CalibrationDecisionStatementOutputUnavailable")
        descriptor = os.open(
            destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600
        )
        try:
            os.write(descriptor, statement)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        created = True
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        OSError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
    ) as error:
        errors.append(str(error) or error.__class__.__name__)
    return {
        "schema": SCHEMA,
        "status": STATUS_READY if created else STATUS_HOLD,
        "statement_created": created,
        "statement_sha256": _sha256(statement) if created else None,
        "private_key_accepted": False,
        "signer_invoked": False,
        "errors": errors,
    }


def _commit_receipt(
    registry: Path, review_digest: str, receipt: Mapping[str, Any]
) -> str:
    if not registry.is_absolute() or registry.is_symlink():
        raise ValueError("CalibrationDecisionRegistryUnavailable")
    info = registry.stat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o077
    ):
        raise ValueError("CalibrationDecisionRegistryUnsafe")
    filename = f"{review_digest}.json"
    destination = registry / filename
    descriptor = os.open(
        destination,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    try:
        payload = _canonical(receipt) + b"\n"
        written = 0
        while written < len(payload):
            written += os.write(descriptor, payload[written:])
        os.fsync(descriptor)
    except BaseException:
        with suppress(OSError):
            destination.unlink()
        raise
    finally:
        os.close(descriptor)
    return filename


def evaluate_temperature_calibration_decision(
    review_receipt_path: str | Path,
    verifier: Any,
    statement_path: str | Path,
    signature_path: str | Path,
    decision_registry: str | Path,
    *,
    prepared_at_utc: str,
    expires_at_utc: str,
    now_utc: str,
) -> dict[str, Any]:
    errors: list[str] = []
    verified = False
    recorded = False
    receipt: dict[str, Any] = {}
    filename: str | None = None
    try:
        _window(prepared_at_utc, expires_at_utc, now_utc)
        review = _review(Path(review_receipt_path))
        fingerprint = _fingerprint(verifier)
        expected = build_temperature_calibration_decision_statement(
            review_receipt_path,
            verifier,
            decision=json.loads(_snapshot(Path(statement_path), MAX_PUBLIC_BYTES))[
                "decision"
            ],
            rationale=json.loads(_snapshot(Path(statement_path), MAX_PUBLIC_BYTES))[
                "rationale"
            ],
            prepared_at_utc=prepared_at_utc,
            expires_at_utc=expires_at_utc,
            now_utc=now_utc,
        )
        statement_bytes = _snapshot(Path(statement_path), MAX_PUBLIC_BYTES)
        statement = json.loads(statement_bytes)
        if (
            not isinstance(statement, dict)
            or set(statement) != _STATEMENT_KEYS
            or statement_bytes != expected
        ):
            raise ValueError("CalibrationDecisionStatementMismatch")
        signature_text = _snapshot(Path(signature_path), MAX_SIGNATURE_BYTES).decode(
            "ascii"
        )
        verified = verifier(KEY_ID, statement_bytes, signature_text) is True
        if not verified:
            raise ValueError("CalibrationDecisionSignatureNotAuthenticated")
        eligible = statement["decision"] == DECISION_ACCEPT
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "status": STATUS_ACCEPTED if eligible else STATUS_HELD,
            "recorded_at_utc": now_utc,
            "decision": statement["decision"],
            "rationale": statement["rationale"],
            "decision_statement_sha256": _sha256(statement_bytes),
            "decision_signature_sha256": _sha256(signature_text.encode("ascii")),
            "review_receipt_sha256": review["review_receipt_sha256"],
            "score_receipt_sha256": review["score_receipt_sha256"],
            "score_sha256": review["score_sha256"],
            "statistical_contract_sha256": review["statistical_contract_sha256"],
            "blinded_manifest_sha256": review["blinded_manifest_sha256"],
            "detector_contract_sha256": review["detector_contract_sha256"],
            "operator_key_fingerprint": fingerprint,
            "statistical_gates_passed": review["statistical_gates_passed"],
            "independent_reconstruction_matched": True,
            "candidate_review_eligible": eligible,
            "candidate_accepted": False,
            **{key: False for key in sorted(_AUTHORITY_KEYS)},
        }
        receipt["receipt_sha256"] = _sha256(receipt)
        if set(receipt) != _RECEIPT_KEYS:
            raise ValueError("CalibrationDecisionReceiptFieldsInvalid")
        filename = _commit_receipt(
            Path(decision_registry), review["review_receipt_sha256"], receipt
        )
        recorded = True
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        KeyError,
        OSError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
    ) as error:
        errors.append(str(error) or error.__class__.__name__)
    accepted = (
        not errors
        and verified
        and recorded
        and receipt.get("candidate_review_eligible") is True
    )
    held = (
        not errors
        and verified
        and recorded
        and receipt.get("candidate_review_eligible") is False
    )
    return {
        "schema": SCHEMA,
        "status": STATUS_ACCEPTED if accepted else STATUS_HELD if held else STATUS_HOLD,
        "decision_signature_verified": verified,
        "decision_recorded": recorded,
        "receipt_filename": filename,
        "receipt_sha256": receipt.get("receipt_sha256") if recorded else None,
        "decision": receipt.get("decision") if recorded else None,
        "candidate_review_eligible": accepted,
        "candidate_accepted": False,
        "decision_registry_writes": int(recorded),
        "score_registry_writes": 0,
        "field_validated": False,
        "production_validated": False,
        "candidate_installed": False,
        "runtime_authority": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "storage_write_authority": False,
        "network_authority": False,
        "automatic_promotion": False,
        "errors": errors,
    }


def pending_temperature_calibration_decision(
    score_review: Mapping[str, Any],
) -> dict[str, Any]:
    ready = (
        score_review.get("status") == STATUS_REVIEWED
        and score_review.get("review_receipt_created") is True
    )
    return {
        "schema": SCHEMA,
        "status": STATUS_REQUIRED if ready else STATUS_HOLD,
        "independent_review_present": ready,
        "operator_decision_present": False,
        "candidate_review_eligible": False,
        "candidate_accepted": False,
        "candidate_installed": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "next_action": "record one authenticated accept-or-hold decision over the exact review"
        if ready
        else "complete independent score review before any operator decision",
        "errors": [] if ready else ["independent score review required"],
    }


__all__ = [
    "DECISION_ACCEPT",
    "DECISION_HOLD",
    "NAMESPACE",
    "RECEIPT_SCHEMA",
    "SCHEMA",
    "STATEMENT_SCHEMA",
    "STATUS_ACCEPTED",
    "STATUS_HELD",
    "STATUS_HOLD",
    "STATUS_READY",
    "build_temperature_calibration_decision_statement",
    "evaluate_temperature_calibration_decision",
    "export_temperature_calibration_decision_statement",
    "pending_temperature_calibration_decision",
]
