"""Independent, read-only reconstruction of an authenticated calibration score."""

from __future__ import annotations

import hashlib
import json
import math
import os
import stat
from collections.abc import Mapping, Sequence
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any, Final

from .ssh_verifier import (
    MAX_ALLOWED_SIGNERS_BYTES,
    MAX_SIGNATURE_BYTES,
    validate_allowed_signers_roster,
)
from .temperature_authenticated_acceptance import KEY_ID
from .temperature_authenticated_label_join import (
    NAMESPACE as LABEL_NAMESPACE,
)
from .temperature_authenticated_label_join import (
    RECEIPT_SCHEMA as SCORE_RECEIPT_SCHEMA,
)
from .temperature_authenticated_label_join import (
    STATEMENT_SCHEMA as LABEL_STATEMENT_SCHEMA,
)
from .temperature_authenticated_label_join import (
    STATUS_SCORED,
)
from .temperature_blinded_cohort_manifest import (
    STATUS_MANIFEST_READY,
    validate_temperature_blinded_cohort_manifest,
)
from .temperature_statistical_calibration_contract import (
    CONFIDENCE_Z,
    validate_temperature_statistical_calibration_contract,
)
from .temperature_statistical_calibration_contract import (
    STATUS_READY as CONTRACT_READY,
)

SCHEMA: Final = "truepanel.aegis-temperature-independent-score-review/v1"
RECEIPT_SCHEMA: Final = (
    "truepanel.aegis-temperature-independent-score-review-receipt/v1"
)
STATUS_REVIEWED: Final = "CALIBRATION_SCORE_INDEPENDENTLY_RECONSTRUCTED"
STATUS_REQUIRED: Final = "ACTION_REQUIRED_INDEPENDENT_SCORE_REVIEW"
STATUS_HOLD: Final = "HOLD"
MAX_PUBLIC_BYTES: Final = 2 * 1024 * 1024
IMPLEMENTATION_ID: Final = "truepanel-independent-score-review-python-v1"

_LABEL_KEYS = {
    "case_id",
    "expected_shared_cooling",
    "first_isolated_threshold_index",
}
_AUTHORITY_KEYS = {
    "field_validated",
    "production_validated",
    "candidate_accepted",
    "candidate_installed",
    "runtime_authority",
    "deployment_authority",
    "hardware_authority",
    "storage_write_authority",
    "network_authority",
    "automatic_promotion",
}
_STATEMENT_KEYS = {
    "schema",
    "namespace",
    "scope",
    "key_id",
    "operator_key_fingerprint",
    "prepared_at_utc",
    "expires_at_utc",
    "statistical_contract_sha256",
    "blinded_manifest_sha256",
    "detector_contract_sha256",
    "case_count",
    "labels_sha256",
    "labels",
    "every_frozen_case_labeled_once",
    "case_exclusions",
    "threshold_changes",
    "single_evaluation_per_detector_contract",
    "label_statement",
    *_AUTHORITY_KEYS,
}
_SCORE_RECEIPT_KEYS = {
    "schema",
    "status",
    "evaluated_at_utc",
    "statistical_contract_sha256",
    "blinded_manifest_sha256",
    "detector_contract_sha256",
    "label_statement_sha256",
    "label_signature_sha256",
    "labels_sha256",
    "operator_key_fingerprint",
    "score",
    "single_evaluation_per_detector_contract",
    "case_exclusions",
    "threshold_changes",
    "receipt_sha256",
    *_AUTHORITY_KEYS,
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
        raise ValueError("ScoreReviewTimeInvalid")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo != UTC:
        raise ValueError("ScoreReviewTimeInvalid")
    return parsed


def _snapshot(path: Path, maximum: int) -> bytes:
    if not path.is_absolute() or not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("ProtectedScoreReviewFileUnavailable")
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
            raise ValueError("ProtectedScoreReviewFileInvalid")
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
        identity = lambda item: (  # noqa: E731
            item.st_dev,
            item.st_ino,
            item.st_mode,
            item.st_uid,
            item.st_size,
            item.st_mtime_ns,
            item.st_ctime_ns,
        )
        if identity(before) != identity(after) or len(payload) > maximum:
            raise ValueError("ProtectedScoreReviewFileChanged")
        return payload
    finally:
        os.close(descriptor)


def _roster_fingerprint(verifier: Any) -> str:
    if (
        getattr(verifier, "namespace", None) != LABEL_NAMESPACE
        or getattr(verifier, "expected_key_ids", None) != (KEY_ID,)
    ):
        raise ValueError("ScoreReviewVerifierPolicyMismatch")
    path = getattr(verifier, "allowed_signers_path", None)
    if not isinstance(path, Path):
        raise ValueError("ScoreReviewVerifierPolicyMismatch")
    roster = validate_allowed_signers_roster(
        _snapshot(path, MAX_ALLOWED_SIGNERS_BYTES), expected_key_ids=(KEY_ID,)
    )
    return roster[KEY_ID]


def _validate_inputs(
    contract: Mapping[str, Any], manifest: Mapping[str, Any]
) -> tuple[str, str]:
    contract_result = validate_temperature_statistical_calibration_contract(contract)
    if contract_result["status"] != CONTRACT_READY:
        raise ValueError("ScoreReviewStatisticalContractNotReady")
    manifest_result = validate_temperature_blinded_cohort_manifest(contract, manifest)
    if manifest_result["status"] != STATUS_MANIFEST_READY:
        raise ValueError("ScoreReviewBlindedManifestNotReady")
    return str(contract_result["contract_sha256"]), str(
        manifest_result["manifest_sha256"]
    )


def _normalize_labels(
    manifest: Mapping[str, Any], labels: Any
) -> list[dict[str, Any]]:
    if not isinstance(labels, list):
        raise ValueError("ScoreReviewLabelsInvalid")
    planned_ids = {item["case_id"] for item in manifest["results"]}
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for label in labels:
        if not isinstance(label, Mapping) or set(label) != _LABEL_KEYS:
            raise ValueError("ScoreReviewLabelFieldsInvalid")
        case_id = label["case_id"]
        if not isinstance(case_id, str) or case_id not in planned_ids:
            raise ValueError("ScoreReviewUnplannedCase")
        if case_id in seen:
            raise ValueError("ScoreReviewDuplicateCase")
        outcome = label["expected_shared_cooling"]
        threshold = label["first_isolated_threshold_index"]
        if type(outcome) is not bool:
            raise ValueError("ScoreReviewOutcomeInvalid")
        if threshold is not None and (type(threshold) is not int or threshold < 0):
            raise ValueError("ScoreReviewThresholdLandmarkInvalid")
        seen.add(case_id)
        normalized.append(
            {
                "case_id": case_id,
                "expected_shared_cooling": outcome,
                "first_isolated_threshold_index": threshold,
            }
        )
    if seen != planned_ids or len(normalized) != manifest["result_count"]:
        raise ValueError("ScoreReviewEveryFrozenCaseRequired")
    normalized.sort(key=lambda item: item["case_id"])
    return normalized


def _wilson(successes: int, trials: int) -> tuple[float, float]:
    if trials <= 0 or not 0 <= successes <= trials:
        raise ValueError("ScoreReviewWilsonPopulationInvalid")
    proportion = successes / trials
    squared = CONFIDENCE_Z * CONFIDENCE_Z
    denominator = 1 + squared / trials
    center = (proportion + squared / (2 * trials)) / denominator
    margin = (
        CONFIDENCE_Z
        * math.sqrt(
            proportion * (1 - proportion) / trials
            + squared / (4 * trials * trials)
        )
        / denominator
    )
    return max(0.0, center - margin), min(1.0, center + margin)


def _p10(values: Sequence[int]) -> int:
    if not values:
        raise ValueError("ScoreReviewLeadPopulationEmpty")
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.10 * len(ordered)) - 1)]


def _reconstruct_score(
    contract: Mapping[str, Any],
    manifest: Mapping[str, Any],
    labels: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    predictions = {item["case_id"]: item for item in manifest["results"]}
    tp = fp = tn = fn = abstentions = 0
    lead_samples: list[int] = []
    for label in labels:
        prediction = predictions[label["case_id"]]
        expected = label["expected_shared_cooling"]
        predicted = prediction["predicted_shared_cooling"]
        if predicted and expected:
            tp += 1
            isolated = label["first_isolated_threshold_index"]
            matched = prediction["first_policy_match_index"]
            if isolated is not None and matched is not None:
                lead_samples.append(isolated - matched)
        elif predicted and not expected:
            fp += 1
        elif not predicted and expected:
            fn += 1
        else:
            tn += 1
    positives = tp + fn
    negatives = tn + fp
    total = len(labels)
    sensitivity = _wilson(tp, positives) if positives else (0.0, 1.0)
    false_positive = _wilson(fp, negatives) if negatives else (0.0, 1.0)
    abstention = _wilson(abstentions, total)
    lead_median = float(median(lead_samples)) if lead_samples else None
    lead_p10 = _p10(lead_samples) if lead_samples else None
    policy = contract["policy"]
    gates = {
        "minimum_positive_cases": positives >= int(policy["minimum_positive_cases"]),
        "minimum_negative_cases": negatives >= int(policy["minimum_negative_cases"]),
        "minimum_threshold_landmark_positive_cases": len(lead_samples)
        >= int(policy["minimum_threshold_landmark_positive_cases"]),
        "sensitivity_wilson_lower": sensitivity[0]
        >= float(policy["minimum_sensitivity_wilson_lower"]),
        "false_positive_rate_wilson_upper": false_positive[1]
        <= float(policy["maximum_false_positive_rate_wilson_upper"]),
        "abstention_rate_wilson_upper": abstention[1]
        <= float(policy["maximum_abstention_rate_wilson_upper"]),
        "median_lead_samples": lead_median is not None
        and lead_median >= int(policy["minimum_median_lead_samples"]),
        "p10_lead_samples": lead_p10 is not None
        and lead_p10 >= int(policy["minimum_p10_lead_samples"]),
    }
    return {
        "case_count": total,
        "positive_cases": positives,
        "negative_cases": negatives,
        "true_positives": tp,
        "false_positives": fp,
        "true_negatives": tn,
        "false_negatives": fn,
        "abstentions": abstentions,
        "threshold_landmark_true_positives": len(lead_samples),
        "sensitivity_point": round(tp / positives, 6) if positives else None,
        "sensitivity_wilson_lower": round(sensitivity[0], 6),
        "false_positive_rate_point": round(fp / negatives, 6)
        if negatives
        else None,
        "false_positive_rate_wilson_upper": round(false_positive[1], 6),
        "abstention_rate_point": round(abstentions / total, 6),
        "abstention_rate_wilson_upper": round(abstention[1], 6),
        "median_lead_samples": lead_median,
        "p10_lead_samples": lead_p10,
        "p10_method": "nearest-rank-ceiling",
        "gates": gates,
        "statistical_gates_passed": all(gates.values()),
    }


def _write_receipt(path: Path, receipt: Mapping[str, Any]) -> None:
    if not path.is_absolute() or path.exists() or path.is_symlink():
        raise ValueError("ScoreReviewOutputUnavailable")
    parent = path.parent
    info = parent.stat()
    if (
        parent.is_symlink()
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o022
    ):
        raise ValueError("ScoreReviewOutputDirectoryInvalid")
    created = False
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
        )
        created = True
        try:
            view = memoryview(_canonical(receipt) + b"\n")
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("ScoreReviewReceiptWriteFailed")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        directory_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        if created:
            with suppress(OSError):
                path.unlink()
        raise


def review_temperature_authenticated_score(
    contract: Mapping[str, Any],
    manifest: Mapping[str, Any],
    verifier: Any,
    label_statement_path: str | Path,
    label_signature_path: str | Path,
    score_receipt_path: str | Path,
    review_receipt_path: str | Path,
    *,
    reviewed_at_utc: str,
) -> dict[str, Any]:
    """Recompute a committed score without accepting labels or writing its registry."""

    errors: list[str] = []
    signature_verified = False
    score_reconstructed = False
    review_created = False
    statistical_gates_passed = False
    review_receipt: dict[str, Any] = {}
    try:
        reviewed_at = _utc(reviewed_at_utc)
        contract_digest, manifest_digest = _validate_inputs(contract, manifest)
        fingerprint = _roster_fingerprint(verifier)

        statement_bytes = _snapshot(Path(label_statement_path), MAX_PUBLIC_BYTES)
        statement = json.loads(statement_bytes)
        if not isinstance(statement, dict) or set(statement) != _STATEMENT_KEYS:
            raise ValueError("ScoreReviewLabelStatementFieldsInvalid")
        if statement_bytes != _canonical(statement):
            raise ValueError("ScoreReviewLabelStatementNotCanonical")
        if (
            statement["schema"] != LABEL_STATEMENT_SCHEMA
            or statement["namespace"] != LABEL_NAMESPACE
            or statement["key_id"] != KEY_ID
            or statement["scope"] != "temperature-calibration-statistical-review-only"
            or statement["operator_key_fingerprint"] != fingerprint
        ):
            raise ValueError("ScoreReviewLabelStatementIdentityMismatch")
        prepared = _utc(statement["prepared_at_utc"])
        expires = _utc(statement["expires_at_utc"])
        if expires <= prepared:
            raise ValueError("ScoreReviewLabelWindowInvalid")
        if (
            statement["statistical_contract_sha256"] != contract_digest
            or statement["blinded_manifest_sha256"] != manifest_digest
            or statement["detector_contract_sha256"]
            != manifest["detector_contract_sha256"]
        ):
            raise ValueError("ScoreReviewLabelStatementSubjectMismatch")
        if any(statement[key] is not False for key in _AUTHORITY_KEYS):
            raise ValueError("ScoreReviewLabelStatementAuthorityEscalation")
        if (
            statement["every_frozen_case_labeled_once"] is not True
            or statement["single_evaluation_per_detector_contract"] is not True
            or statement["case_exclusions"] != []
            or statement["threshold_changes"] != []
        ):
            raise ValueError("ScoreReviewLabelStatementPolicyMismatch")
        labels = _normalize_labels(manifest, statement["labels"])
        if (
            statement["case_count"] != len(labels)
            or statement["labels_sha256"] != _sha256(labels)
        ):
            raise ValueError("ScoreReviewLabelsDigestMismatch")

        signature_text = _snapshot(
            Path(label_signature_path), MAX_SIGNATURE_BYTES
        ).decode("ascii")
        signature_verified = verifier(KEY_ID, statement_bytes, signature_text) is True
        if not signature_verified:
            raise ValueError("ScoreReviewLabelSignatureNotAuthenticated")

        receipt_bytes = _snapshot(Path(score_receipt_path), MAX_PUBLIC_BYTES)
        receipt = json.loads(receipt_bytes)
        if not isinstance(receipt, dict) or set(receipt) != _SCORE_RECEIPT_KEYS:
            raise ValueError("ScoreReviewScoreReceiptFieldsInvalid")
        if receipt_bytes != _canonical(receipt) + b"\n":
            raise ValueError("ScoreReviewScoreReceiptNotCanonical")
        claimed_receipt_digest = receipt["receipt_sha256"]
        unsigned_receipt = dict(receipt)
        del unsigned_receipt["receipt_sha256"]
        if claimed_receipt_digest != _sha256(unsigned_receipt):
            raise ValueError("ScoreReviewScoreReceiptDigestMismatch")
        evaluated = _utc(receipt["evaluated_at_utc"])
        if evaluated < prepared or evaluated >= expires or reviewed_at < evaluated:
            raise ValueError("ScoreReviewOrderingInvalid")
        if (
            receipt["schema"] != SCORE_RECEIPT_SCHEMA
            or receipt["status"] != STATUS_SCORED
            or receipt["statistical_contract_sha256"] != contract_digest
            or receipt["blinded_manifest_sha256"] != manifest_digest
            or receipt["detector_contract_sha256"]
            != manifest["detector_contract_sha256"]
            or receipt["label_statement_sha256"] != _sha256(statement_bytes)
            or receipt["label_signature_sha256"]
            != _sha256(signature_text.encode("ascii"))
            or receipt["labels_sha256"] != statement["labels_sha256"]
            or receipt["operator_key_fingerprint"] != fingerprint
        ):
            raise ValueError("ScoreReviewScoreReceiptSubjectMismatch")
        if any(receipt[key] is not False for key in _AUTHORITY_KEYS):
            raise ValueError("ScoreReviewScoreReceiptAuthorityEscalation")
        if (
            receipt["single_evaluation_per_detector_contract"] is not True
            or receipt["case_exclusions"] != []
            or receipt["threshold_changes"] != []
        ):
            raise ValueError("ScoreReviewScoreReceiptPolicyMismatch")

        reconstructed = _reconstruct_score(contract, manifest, labels)
        if receipt["score"] != reconstructed:
            raise ValueError("ScoreReviewIndependentReconstructionMismatch")
        score_reconstructed = True
        statistical_gates_passed = reconstructed["statistical_gates_passed"]
        review_receipt = {
            "schema": RECEIPT_SCHEMA,
            "status": STATUS_REVIEWED,
            "reviewed_at_utc": reviewed_at_utc,
            "implementation_id": IMPLEMENTATION_ID,
            "statistical_contract_sha256": contract_digest,
            "blinded_manifest_sha256": manifest_digest,
            "detector_contract_sha256": manifest["detector_contract_sha256"],
            "label_statement_sha256": _sha256(statement_bytes),
            "label_signature_sha256": _sha256(signature_text.encode("ascii")),
            "score_receipt_sha256": claimed_receipt_digest,
            "score_sha256": _sha256(reconstructed),
            "score": reconstructed,
            "independent_reconstruction_matched": True,
            "statistical_gates_passed": statistical_gates_passed,
            "score_registry_read_only": True,
            "score_re_evaluated": False,
            "labels_changed": False,
            "thresholds_changed": False,
            "case_exclusions": [],
            "limitations": [
                "deterministic simulation evidence is not field validation",
                "score review grants no acceptance or operational authority",
            ],
            **{key: False for key in sorted(_AUTHORITY_KEYS)},
        }
        review_receipt["review_receipt_sha256"] = _sha256(review_receipt)
        _write_receipt(Path(review_receipt_path), review_receipt)
        review_created = True
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        OSError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
    ) as error:
        errors.append(str(error) or error.__class__.__name__)
    reviewed = not errors and signature_verified and score_reconstructed and review_created
    return {
        "schema": SCHEMA,
        "status": STATUS_REVIEWED if reviewed else STATUS_HOLD,
        "implementation_id": IMPLEMENTATION_ID,
        "label_signature_verified": signature_verified,
        "score_reconstructed": score_reconstructed,
        "review_receipt_created": review_created,
        "review_receipt_sha256": review_receipt.get("review_receipt_sha256")
        if reviewed
        else None,
        "statistical_gates_passed": statistical_gates_passed if reviewed else False,
        "passing_and_failing_scores_reviewable": reviewed,
        "score_registry_read_only": True,
        "score_registry_writes": 0,
        "score_re_evaluated": False,
        "labels_changed": False,
        "thresholds_changed": False,
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
        "errors": errors,
    }


def pending_temperature_score_review(
    label_join: Mapping[str, Any],
) -> dict[str, Any]:
    """Expose the read-only next gate without inventing a score review."""

    score_ready = (
        label_join.get("status") == STATUS_SCORED
        and label_join.get("score_committed") is True
        and label_join.get("eligible_for_independent_score_review") is True
    )
    return {
        "schema": SCHEMA,
        "status": STATUS_REQUIRED if score_ready else STATUS_HOLD,
        "score_receipt_present": score_ready,
        "label_signature_verified": False,
        "score_reconstructed": False,
        "review_receipt_created": False,
        "statistical_gates_passed": False,
        "score_registry_read_only": True,
        "score_registry_writes": 0,
        "score_re_evaluated": False,
        "field_validated": False,
        "candidate_accepted": False,
        "candidate_installed": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "next_action": (
            "commit one authenticated immutable score before independent review"
            if not score_ready
            else "reconstruct the committed pass or fail score without changing it"
        ),
        "errors": [] if score_ready else ["immutable score receipt required"],
    }


__all__ = [
    "IMPLEMENTATION_ID",
    "RECEIPT_SCHEMA",
    "SCHEMA",
    "STATUS_HOLD",
    "STATUS_REQUIRED",
    "STATUS_REVIEWED",
    "pending_temperature_score_review",
    "review_temperature_authenticated_score",
]
