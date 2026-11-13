"""Independent concurrence over one authenticated replay evidence review."""

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
from .temperature_authenticated_replay_review import (
    STATUS_ACCEPTED as PRIMARY_ACCEPTED,
)
from .temperature_authenticated_replay_review import (
    verify_recorded_temperature_authenticated_replay_review,
)
from .temperature_calibration_candidate_appraisal import (
    MAX_PUBLIC_BYTES,
    _canonical,
    _snapshot,
)

SCHEMA: Final = "truepanel.aegis-temperature-two-person-replay-review/v1"
STATEMENT_SCHEMA: Final = (
    "truepanel.aegis-temperature-two-person-replay-review-statement/v1"
)
RECEIPT_SCHEMA: Final = (
    "truepanel.aegis-temperature-two-person-replay-review-receipt/v1"
)
NAMESPACE: Final = "truepanel-aegis-temperature-two-person-replay-review-v1@truepanel"
REVIEWER_KEY_ID: Final = "independent-replay-reviewer"
DECISION_CONCUR: Final = "CONCUR_ACCEPT_EVIDENCE"
DECISION_DISSENT: Final = "DISSENT_HOLD_EVIDENCE"
STATUS_READY: Final = "READY_FOR_INDEPENDENT_REVIEW_SIGNATURE"
STATUS_QUORUM: Final = "TWO_PERSON_EVIDENCE_QUORUM_FOR_MANUAL_CALIBRATION_CONSIDERATION"
STATUS_HELD: Final = "INDEPENDENT_REVIEW_HOLD_RECORDED"
STATUS_REQUIRED: Final = "ACTION_REQUIRED_INDEPENDENT_REPLAY_REVIEW"
STATUS_HOLD: Final = "HOLD"
MAX_WINDOW: Final = timedelta(hours=2)

_DENIED = (
    "field_validated",
    "production_validated",
    "candidate_accepted",
    "candidate_installed",
    "capture_authority",
    "runtime_authority",
    "deployment_authority",
    "hardware_authority",
    "storage_write_authority",
    "network_authority",
    "automatic_promotion",
)
_STATEMENT_KEYS = {
    "schema",
    "namespace",
    "scope",
    "key_id",
    "reviewer_key_fingerprint",
    "prepared_at_utc",
    "expires_at_utc",
    "decision",
    "rationale",
    "primary_review_receipt_sha256",
    "replay_receipt_sha256",
    "primary_operator_key_fingerprint",
    "independent_identity_required",
    "two_person_quorum",
    "manual_calibration_consideration",
    *_DENIED,
}
_RECEIPT_KEYS = {
    "schema",
    "status",
    "recorded_at_utc",
    "decision",
    "rationale",
    "concurrence_statement_sha256",
    "concurrence_signature_sha256",
    "primary_review_receipt_sha256",
    "replay_receipt_sha256",
    "primary_operator_key_fingerprint",
    "reviewer_key_fingerprint",
    "independent_identity_verified",
    "two_person_quorum",
    "manual_calibration_consideration",
    "receipt_sha256",
    *_DENIED,
}
_RATIONALES = {
    "independently-reconstructed-and-concurred",
    "independent-review-caution",
    "evidence-reconstruction-mismatch",
    "external-review-required",
}


def _sha(value: Any) -> str:
    return hashlib.sha256(
        value if isinstance(value, bytes) else _canonical(value)
    ).hexdigest()


def _window(prepared: str, expires: str, now: str) -> None:
    def parse(value: str) -> datetime:
        if not isinstance(value, str) or not value.endswith("Z"):
            raise ValueError("TwoPersonReplayReviewTimeInvalid")
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
        if parsed.tzinfo != UTC:
            raise ValueError("TwoPersonReplayReviewTimeInvalid")
        return parsed

    start, end, current = map(parse, (prepared, expires, now))
    if end <= start or end - start > MAX_WINDOW or current < start or current >= end:
        raise ValueError("TwoPersonReplayReviewWindowInvalid")


def _fingerprint(verifier: Any) -> str:
    if getattr(verifier, "namespace", None) != NAMESPACE or getattr(
        verifier, "expected_key_ids", None
    ) != (REVIEWER_KEY_ID,):
        raise ValueError("TwoPersonReplayReviewVerifierPolicyMismatch")
    path = getattr(verifier, "allowed_signers_path", None)
    if not isinstance(path, Path):
        raise ValueError("TwoPersonReplayReviewVerifierPolicyMismatch")
    return validate_allowed_signers_roster(
        _snapshot(path, MAX_ALLOWED_SIGNERS_BYTES), expected_key_ids=(REVIEWER_KEY_ID,)
    )[REVIEWER_KEY_ID]


def build_temperature_two_person_replay_review_statement(
    replay_receipt_path: str | Path,
    primary_verifier: Any,
    primary_statement_path: str | Path,
    primary_signature_path: str | Path,
    primary_receipt_path: str | Path,
    reviewer_verifier: Any,
    *,
    decision: str,
    rationale: str,
    prepared_at_utc: str,
    expires_at_utc: str,
    now_utc: str,
) -> bytes:
    _window(prepared_at_utc, expires_at_utc, now_utc)
    primary = verify_recorded_temperature_authenticated_replay_review(
        replay_receipt_path,
        primary_verifier,
        primary_statement_path,
        primary_signature_path,
        primary_receipt_path,
        now_utc=now_utc,
    )
    if (
        primary["status"] != PRIMARY_ACCEPTED
        or primary["manual_calibration_consideration"] is not True
    ):
        raise ValueError("TwoPersonReplayReviewPrimaryNotAccepted")
    if (
        decision not in {DECISION_CONCUR, DECISION_DISSENT}
        or rationale not in _RATIONALES
        or (
            (decision == DECISION_CONCUR)
            != (rationale == "independently-reconstructed-and-concurred")
        )
    ):
        raise ValueError("TwoPersonReplayReviewChoiceInvalid")
    reviewer = _fingerprint(reviewer_verifier)
    if reviewer == primary["operator_key_fingerprint"]:
        raise ValueError("TwoPersonReplayReviewIdentityNotIndependent")
    concurred = decision == DECISION_CONCUR
    return _canonical(
        {
            "schema": STATEMENT_SCHEMA,
            "namespace": NAMESPACE,
            "scope": "independent-replay-evidence-concurrence-only",
            "key_id": REVIEWER_KEY_ID,
            "reviewer_key_fingerprint": reviewer,
            "prepared_at_utc": prepared_at_utc,
            "expires_at_utc": expires_at_utc,
            "decision": decision,
            "rationale": rationale,
            "primary_review_receipt_sha256": primary["receipt_sha256"],
            "replay_receipt_sha256": primary["replay_receipt_sha256"],
            "primary_operator_key_fingerprint": primary["operator_key_fingerprint"],
            "independent_identity_required": True,
            "two_person_quorum": concurred,
            "manual_calibration_consideration": concurred,
            **{key: False for key in sorted(_DENIED)},
        }
    )


def export_temperature_two_person_replay_review_statement(
    *args: Any, output_path: str | Path, **kwargs: Any
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        statement = build_temperature_two_person_replay_review_statement(
            *args, **kwargs
        )
        destination = Path(output_path)
        if (
            not destination.is_absolute()
            or destination.exists()
            or destination.is_symlink()
        ):
            raise ValueError("TwoPersonReplayReviewOutputUnavailable")
        descriptor = os.open(
            destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600
        )
        try:
            os.write(descriptor, statement)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return {
            "schema": SCHEMA,
            "status": STATUS_READY,
            "statement_created": True,
            "statement_sha256": _sha(statement),
            "private_key_accepted": False,
            "signer_invoked": False,
            "errors": [],
        }
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
    return {
        "schema": SCHEMA,
        "status": STATUS_HOLD,
        "statement_created": False,
        "statement_sha256": None,
        "private_key_accepted": False,
        "signer_invoked": False,
        "errors": errors,
    }


def _commit(registry: Path, digest: str, receipt: Mapping[str, Any]) -> str:
    if not registry.is_absolute() or registry.is_symlink():
        raise ValueError("TwoPersonReplayReviewRegistryUnavailable")
    info = registry.stat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o077
    ):
        raise ValueError("TwoPersonReplayReviewRegistryUnsafe")
    destination = registry / f"{digest}.json"
    descriptor = os.open(
        destination,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    try:
        os.write(descriptor, _canonical(receipt) + b"\n")
        os.fsync(descriptor)
    except BaseException:
        with suppress(OSError):
            destination.unlink()
        raise
    finally:
        os.close(descriptor)
    return destination.name


def evaluate_temperature_two_person_replay_review(
    replay_receipt_path: str | Path,
    primary_verifier: Any,
    primary_statement_path: str | Path,
    primary_signature_path: str | Path,
    primary_receipt_path: str | Path,
    reviewer_verifier: Any,
    statement_path: str | Path,
    signature_path: str | Path,
    registry_path: str | Path,
    *,
    now_utc: str,
) -> dict[str, Any]:
    errors: list[str] = []
    receipt: dict[str, Any] = {}
    filename = None
    verified = False
    try:
        primary = verify_recorded_temperature_authenticated_replay_review(
            replay_receipt_path,
            primary_verifier,
            primary_statement_path,
            primary_signature_path,
            primary_receipt_path,
            now_utc=now_utc,
        )
        statement_bytes = _snapshot(Path(statement_path), MAX_PUBLIC_BYTES)
        statement = json.loads(statement_bytes)
        if not isinstance(statement, dict) or set(statement) != _STATEMENT_KEYS:
            raise ValueError("TwoPersonReplayReviewStatementFieldsInvalid")
        expected = build_temperature_two_person_replay_review_statement(
            replay_receipt_path,
            primary_verifier,
            primary_statement_path,
            primary_signature_path,
            primary_receipt_path,
            reviewer_verifier,
            decision=statement["decision"],
            rationale=statement["rationale"],
            prepared_at_utc=statement["prepared_at_utc"],
            expires_at_utc=statement["expires_at_utc"],
            now_utc=now_utc,
        )
        if statement_bytes != expected:
            raise ValueError("TwoPersonReplayReviewStatementMismatch")
        signature = _snapshot(Path(signature_path), MAX_SIGNATURE_BYTES)
        verified = (
            reviewer_verifier(
                REVIEWER_KEY_ID, statement_bytes, signature.decode("ascii")
            )
            is True
        )
        if not verified:
            raise ValueError("TwoPersonReplayReviewSignatureNotAuthenticated")
        concurred = statement["decision"] == DECISION_CONCUR
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "status": STATUS_QUORUM if concurred else STATUS_HELD,
            "recorded_at_utc": now_utc,
            "decision": statement["decision"],
            "rationale": statement["rationale"],
            "concurrence_statement_sha256": _sha(statement_bytes),
            "concurrence_signature_sha256": _sha(signature),
            "primary_review_receipt_sha256": primary["receipt_sha256"],
            "replay_receipt_sha256": primary["replay_receipt_sha256"],
            "primary_operator_key_fingerprint": primary["operator_key_fingerprint"],
            "reviewer_key_fingerprint": statement["reviewer_key_fingerprint"],
            "independent_identity_verified": True,
            "two_person_quorum": concurred,
            "manual_calibration_consideration": concurred,
            **{key: False for key in sorted(_DENIED)},
        }
        receipt["receipt_sha256"] = _sha(receipt)
        if set(receipt) != _RECEIPT_KEYS:
            raise ValueError("TwoPersonReplayReviewReceiptFieldsInvalid")
        filename = _commit(Path(registry_path), primary["receipt_sha256"], receipt)
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
    recorded = filename is not None and not errors
    quorum = recorded and receipt.get("two_person_quorum") is True
    return {
        "schema": SCHEMA,
        "status": STATUS_QUORUM if quorum else STATUS_HELD if recorded else STATUS_HOLD,
        "independent_signature_verified": verified,
        "concurrence_recorded": recorded,
        "two_person_quorum": quorum,
        "manual_calibration_consideration": quorum,
        "receipt_filename": filename,
        "receipt_sha256": receipt.get("receipt_sha256") if recorded else None,
        **{key: False for key in _DENIED},
        "errors": errors,
    }


def pending_temperature_two_person_replay_review(
    primary: Mapping[str, Any],
) -> dict[str, Any]:
    ready = (
        primary.get("review_recorded") is True
        and primary.get("manual_calibration_consideration") is True
    )
    return {
        "schema": SCHEMA,
        "status": STATUS_REQUIRED if ready else STATUS_HOLD,
        "primary_review_present": primary.get("review_recorded") is True,
        "independent_signature_verified": False,
        "concurrence_recorded": False,
        "two_person_quorum": False,
        "manual_calibration_consideration": False,
        **{key: False for key in _DENIED},
        "next_action": "A distinct reviewer must independently reconstruct and sign CONCUR or DISSENT; no single signature creates quorum.",
    }


__all__ = [
    "DECISION_CONCUR",
    "DECISION_DISSENT",
    "NAMESPACE",
    "REVIEWER_KEY_ID",
    "SCHEMA",
    "STATUS_QUORUM",
    "STATUS_HELD",
    "STATUS_HOLD",
    "STATUS_READY",
    "build_temperature_two_person_replay_review_statement",
    "evaluate_temperature_two_person_replay_review",
    "export_temperature_two_person_replay_review_statement",
    "pending_temperature_two_person_replay_review",
]
