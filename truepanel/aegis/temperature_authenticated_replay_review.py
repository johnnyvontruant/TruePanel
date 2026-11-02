"""Authenticated human disposition of one exact label-blind replay receipt."""

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
from .temperature_calibration_candidate_appraisal import (
    MAX_PUBLIC_BYTES,
    _canonical,
    _snapshot,
)
from .temperature_label_blind_passive_replay import (
    RECEIPT_SCHEMA as REPLAY_RECEIPT_SCHEMA,
)
from .temperature_label_blind_passive_replay import (
    STATUS_READY as REPLAY_READY,
)

SCHEMA: Final = "truepanel.aegis-temperature-authenticated-replay-review/v1"
STATEMENT_SCHEMA: Final = (
    "truepanel.aegis-temperature-authenticated-replay-review-statement/v1"
)
RECEIPT_SCHEMA: Final = (
    "truepanel.aegis-temperature-authenticated-replay-review-receipt/v1"
)
NAMESPACE: Final = (
    "truepanel-aegis-temperature-authenticated-replay-review-v1@truepanel"
)
SCOPE: Final = "manual-replay-evidence-disposition-only"
DECISION_ACCEPT: Final = "ACCEPT_EVIDENCE"
DECISION_HOLD: Final = "HOLD_EVIDENCE"
STATUS_READY: Final = "READY_FOR_OFFLINE_REPLAY_REVIEW_SIGNATURE"
STATUS_ACCEPTED: Final = "EVIDENCE_ACCEPTED_FOR_MANUAL_CALIBRATION_CONSIDERATION"
STATUS_HELD: Final = "REPLAY_EVIDENCE_HOLD_RECORDED"
STATUS_REQUIRED: Final = "ACTION_REQUIRED_AUTHENTICATED_REPLAY_REVIEW"
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
_REPLAY_DENIED = tuple(key for key in _DENIED if key != "capture_authority")
_REPLAY_REQUIRED = {
    "schema",
    "status",
    "replayed_at_utc",
    "receipt_sha256",
    "label_blind",
    "labels_present",
    "probable_root_cause",
    "confidence",
    "supporting_evidence",
    "first_shared_cooling_match_sample",
    "first_isolated_threshold_sample",
    "lead_samples",
    "coverage_total",
    "coverage_trusted",
    "coverage_gaps",
    "passive_replay_performed",
    "live_capture_performed",
    *_REPLAY_DENIED,
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
    "replay_receipt_sha256",
    "probable_root_cause",
    "confidence",
    "supporting_signal_count",
    "coverage",
    "proof",
    "manual_calibration_consideration",
    *_DENIED,
}
_RECEIPT_KEYS = {
    "schema",
    "status",
    "recorded_at_utc",
    "decision",
    "rationale",
    "review_statement_sha256",
    "review_signature_sha256",
    "replay_receipt_sha256",
    "operator_key_fingerprint",
    "manual_calibration_consideration",
    "receipt_sha256",
    *_DENIED,
}
_RATIONALES = {
    "evidence-and-method-reviewed",
    "operator-caution",
    "insufficient-independent-review",
    "external-review-required",
}


def _sha(value: Any) -> str:
    return hashlib.sha256(
        value if isinstance(value, bytes) else _canonical(value)
    ).hexdigest()


def _window(prepared: str, expires: str, now: str) -> None:
    def parse(value: str) -> datetime:
        if not isinstance(value, str) or not value.endswith("Z"):
            raise ValueError("ReplayReviewTimeInvalid")
        result = datetime.fromisoformat(value[:-1] + "+00:00")
        if result.tzinfo != UTC:
            raise ValueError("ReplayReviewTimeInvalid")
        return result

    start, end, current = map(parse, (prepared, expires, now))
    if end <= start or end - start > MAX_WINDOW or current < start or current >= end:
        raise ValueError("ReplayReviewWindowInvalid")


def _fingerprint(verifier: Any) -> str:
    if getattr(verifier, "namespace", None) != NAMESPACE or getattr(
        verifier, "expected_key_ids", None
    ) != (KEY_ID,):
        raise ValueError("ReplayReviewVerifierPolicyMismatch")
    path = getattr(verifier, "allowed_signers_path", None)
    if not isinstance(path, Path):
        raise ValueError("ReplayReviewVerifierPolicyMismatch")
    return validate_allowed_signers_roster(
        _snapshot(path, MAX_ALLOWED_SIGNERS_BYTES), expected_key_ids=(KEY_ID,)
    )[KEY_ID]


def _replay(path: Path) -> dict[str, Any]:
    payload = _snapshot(path, MAX_PUBLIC_BYTES)
    value = json.loads(payload)
    if (
        not isinstance(value, dict)
        or payload != _canonical(value) + b"\n"
        or not _REPLAY_REQUIRED.issubset(value)
    ):
        raise ValueError("ReplayReviewEvidenceInvalid")
    unsigned = dict(value)
    claimed = unsigned.pop("receipt_sha256")
    if claimed != _sha(unsigned):
        raise ValueError("ReplayReviewEvidenceDigestMismatch")
    if (
        value["schema"] != REPLAY_RECEIPT_SCHEMA
        or value["status"] != REPLAY_READY
        or value["label_blind"] is not True
        or value["labels_present"] is not False
        or value["probable_root_cause"] != "Shared chassis cooling degradation"
        or value["confidence"] != 0.95
        or len(value["supporting_evidence"]) != 5
        or value["coverage_total"] != 8
        or value["coverage_trusted"] != 8
        or value["coverage_gaps"] != 0
        or value["first_shared_cooling_match_sample"] != 19
        or value["first_isolated_threshold_sample"] != 46
        or value["lead_samples"] != 27
        or value["passive_replay_performed"] is not True
        or value["live_capture_performed"] is not False
        or any(value[k] is not False for k in _REPLAY_DENIED)
    ):
        raise ValueError("ReplayReviewEvidencePolicyMismatch")
    return value


def build_temperature_authenticated_replay_review_statement(
    replay_receipt_path: str | Path,
    verifier: Any,
    *,
    decision: str,
    rationale: str,
    prepared_at_utc: str,
    expires_at_utc: str,
    now_utc: str,
) -> bytes:
    _window(prepared_at_utc, expires_at_utc, now_utc)
    replay = _replay(Path(replay_receipt_path))
    if (
        decision not in {DECISION_ACCEPT, DECISION_HOLD}
        or rationale not in _RATIONALES
        or (
            (decision == DECISION_ACCEPT)
            != (rationale == "evidence-and-method-reviewed")
        )
    ):
        raise ValueError("ReplayReviewChoiceInvalid")
    accepted = decision == DECISION_ACCEPT
    return _canonical(
        {
            "schema": STATEMENT_SCHEMA,
            "namespace": NAMESPACE,
            "scope": SCOPE,
            "key_id": KEY_ID,
            "operator_key_fingerprint": _fingerprint(verifier),
            "prepared_at_utc": prepared_at_utc,
            "expires_at_utc": expires_at_utc,
            "decision": decision,
            "rationale": rationale,
            "replay_receipt_sha256": replay["receipt_sha256"],
            "probable_root_cause": replay["probable_root_cause"],
            "confidence": replay["confidence"],
            "supporting_signal_count": len(replay["supporting_evidence"]),
            "coverage": {"total": 8, "trusted": 8, "gaps": 0},
            "proof": {
                "shared_cooling_match_sample": 19,
                "isolated_threshold_sample": 46,
                "lead_samples": 27,
            },
            "manual_calibration_consideration": accepted,
            **{k: False for k in sorted(_DENIED)},
        }
    )


def export_temperature_authenticated_replay_review_statement(
    replay_receipt_path: str | Path,
    verifier: Any,
    output_path: str | Path,
    **kwargs: Any,
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        statement = build_temperature_authenticated_replay_review_statement(
            replay_receipt_path, verifier, **kwargs
        )
        destination = Path(output_path)
        if (
            not destination.is_absolute()
            or destination.exists()
            or destination.is_symlink()
        ):
            raise ValueError("ReplayReviewStatementOutputUnavailable")
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
        raise ValueError("ReplayReviewRegistryUnavailable")
    info = registry.stat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o077
    ):
        raise ValueError("ReplayReviewRegistryUnsafe")
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


def evaluate_temperature_authenticated_replay_review(
    replay_receipt_path: str | Path,
    verifier: Any,
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
        replay = _replay(Path(replay_receipt_path))
        statement_bytes = _snapshot(Path(statement_path), MAX_PUBLIC_BYTES)
        statement = json.loads(statement_bytes)
        if not isinstance(statement, dict) or set(statement) != _STATEMENT_KEYS:
            raise ValueError("ReplayReviewStatementFieldsInvalid")
        expected = build_temperature_authenticated_replay_review_statement(
            replay_receipt_path,
            verifier,
            decision=statement["decision"],
            rationale=statement["rationale"],
            prepared_at_utc=statement["prepared_at_utc"],
            expires_at_utc=statement["expires_at_utc"],
            now_utc=now_utc,
        )
        if statement_bytes != expected:
            raise ValueError("ReplayReviewStatementMismatch")
        signature = _snapshot(Path(signature_path), MAX_SIGNATURE_BYTES)
        verified = verifier(KEY_ID, statement_bytes, signature.decode("ascii")) is True
        if not verified:
            raise ValueError("ReplayReviewSignatureNotAuthenticated")
        accepted = statement["decision"] == DECISION_ACCEPT
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "status": STATUS_ACCEPTED if accepted else STATUS_HELD,
            "recorded_at_utc": now_utc,
            "decision": statement["decision"],
            "rationale": statement["rationale"],
            "review_statement_sha256": _sha(statement_bytes),
            "review_signature_sha256": _sha(signature),
            "replay_receipt_sha256": replay["receipt_sha256"],
            "operator_key_fingerprint": statement["operator_key_fingerprint"],
            "manual_calibration_consideration": accepted,
            **{k: False for k in sorted(_DENIED)},
        }
        receipt["receipt_sha256"] = _sha(receipt)
        if set(receipt) != _RECEIPT_KEYS:
            raise ValueError("ReplayReviewReceiptFieldsInvalid")
        filename = _commit(Path(registry_path), replay["receipt_sha256"], receipt)
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
    accepted = recorded and receipt.get("manual_calibration_consideration") is True
    return {
        "schema": SCHEMA,
        "status": STATUS_ACCEPTED
        if accepted
        else STATUS_HELD
        if recorded
        else STATUS_HOLD,
        "review_signature_verified": verified,
        "review_recorded": recorded,
        "receipt_filename": filename,
        "receipt_sha256": receipt.get("receipt_sha256") if recorded else None,
        "decision": receipt.get("decision") if recorded else None,
        "manual_calibration_consideration": accepted,
        **{k: False for k in _DENIED},
        "errors": errors,
    }


def pending_temperature_authenticated_replay_review(
    replay: Mapping[str, Any],
) -> dict[str, Any]:
    ready = replay.get("replay_receipt_written") is True
    return {
        "schema": SCHEMA,
        "status": STATUS_REQUIRED if ready else STATUS_HOLD,
        "replay_receipt_present": ready,
        "review_signature_verified": False,
        "review_recorded": False,
        "manual_calibration_consideration": False,
        **{k: False for k in _DENIED},
        "next_action": "Sign one exact ACCEPT_EVIDENCE or HOLD_EVIDENCE statement offline; acceptance permits manual calibration consideration only.",
    }


__all__ = [
    "DECISION_ACCEPT",
    "DECISION_HOLD",
    "NAMESPACE",
    "SCHEMA",
    "STATUS_ACCEPTED",
    "STATUS_HELD",
    "STATUS_HOLD",
    "STATUS_READY",
    "build_temperature_authenticated_replay_review_statement",
    "evaluate_temperature_authenticated_replay_review",
    "export_temperature_authenticated_replay_review_statement",
    "pending_temperature_authenticated_replay_review",
]
