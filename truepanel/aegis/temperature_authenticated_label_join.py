"""One-shot authenticated label join and statistical score receipt."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from collections.abc import Mapping, Sequence
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any, Final

from .evidence_gate import wilson_interval
from .ssh_verifier import (
    MAX_ALLOWED_SIGNERS_BYTES,
    MAX_SIGNATURE_BYTES,
    validate_allowed_signers_roster,
)
from .temperature_authenticated_acceptance import KEY_ID
from .temperature_blinded_cohort_manifest import (
    STATUS_MANIFEST_READY,
    validate_temperature_blinded_cohort_manifest,
)
from .temperature_statistical_calibration_contract import (
    STATUS_READY as CONTRACT_READY,
)
from .temperature_statistical_calibration_contract import (
    validate_temperature_statistical_calibration_contract,
)

SCHEMA: Final = "truepanel.aegis-temperature-authenticated-label-join/v1"
STATEMENT_SCHEMA: Final = (
    "truepanel.aegis-temperature-authenticated-label-join-statement/v1"
)
RECEIPT_SCHEMA: Final = (
    "truepanel.aegis-temperature-statistical-score-receipt/v1"
)
NAMESPACE: Final = "truepanel-aegis-temperature-label-join-v1@truepanel"
SCOPE: Final = "temperature-calibration-statistical-review-only"
STATUS_READY: Final = "READY_FOR_OFFLINE_LABEL_JOIN_SIGNATURE"
STATUS_SCORED: Final = "AUTHENTICATED_CALIBRATION_SCORE_REVIEW_READY"
STATUS_REQUIRED: Final = "ACTION_REQUIRED_AUTHENTICATED_LABEL_JOIN"
STATUS_HOLD: Final = "HOLD"
MAX_WINDOW: Final = timedelta(hours=2)
MAX_PUBLIC_BYTES: Final = 2 * 1024 * 1024
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_LABEL_KEYS = {
    "case_id",
    "expected_shared_cooling",
    "first_isolated_threshold_index",
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
        raise ValueError("LabelJoinTimeInvalid")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo != UTC:
        raise ValueError("LabelJoinTimeInvalid")
    return parsed


def _window(prepared_at_utc: str, expires_at_utc: str, now_utc: str) -> None:
    prepared = _utc(prepared_at_utc)
    expires = _utc(expires_at_utc)
    now = _utc(now_utc)
    if expires <= prepared or expires - prepared > MAX_WINDOW:
        raise ValueError("LabelJoinWindowInvalid")
    if now < prepared or now >= expires:
        raise ValueError("LabelJoinExpiredOrNotYetValid")


def _snapshot(path: Path, maximum: int) -> bytes:
    if not path.is_absolute() or not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("ProtectedLabelJoinFileUnavailable")
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
            raise ValueError("ProtectedLabelJoinFileInvalid")
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
            raise ValueError("ProtectedLabelJoinFileChanged")
        return payload
    finally:
        os.close(descriptor)


def _fingerprint(verifier: Any) -> str:
    if (
        getattr(verifier, "namespace", None) != NAMESPACE
        or getattr(verifier, "expected_key_ids", None) != (KEY_ID,)
    ):
        raise ValueError("LabelJoinVerifierPolicyMismatch")
    path = getattr(verifier, "allowed_signers_path", None)
    if not isinstance(path, Path):
        raise ValueError("LabelJoinVerifierPolicyMismatch")
    roster = validate_allowed_signers_roster(
        _snapshot(path, MAX_ALLOWED_SIGNERS_BYTES), expected_key_ids=(KEY_ID,)
    )
    return roster[KEY_ID]


def _validate_inputs(
    contract: Mapping[str, Any], manifest: Mapping[str, Any]
) -> tuple[str, str]:
    contract_result = validate_temperature_statistical_calibration_contract(contract)
    if contract_result["status"] != CONTRACT_READY:
        raise ValueError("LabelJoinStatisticalContractNotReady")
    manifest_result = validate_temperature_blinded_cohort_manifest(contract, manifest)
    if manifest_result["status"] != STATUS_MANIFEST_READY:
        raise ValueError("LabelJoinBlindedManifestNotReady")
    return str(contract_result["contract_sha256"]), str(
        manifest_result["manifest_sha256"]
    )


def _normalize_labels(
    manifest: Mapping[str, Any], labels: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    planned_ids = {item["case_id"] for item in manifest["results"]}
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for label in labels:
        if not isinstance(label, Mapping) or set(label) != _LABEL_KEYS:
            raise ValueError("LabelJoinLabelFieldsInvalid")
        case_id = label["case_id"]
        if not isinstance(case_id, str) or case_id not in planned_ids:
            raise ValueError("LabelJoinUnplannedCase")
        if case_id in seen:
            raise ValueError("LabelJoinDuplicateCase")
        if type(label["expected_shared_cooling"]) is not bool:
            raise ValueError("LabelJoinOutcomeInvalid")
        threshold = label["first_isolated_threshold_index"]
        if threshold is not None and (
            type(threshold) is not int or threshold < 0
        ):
            raise ValueError("LabelJoinThresholdLandmarkInvalid")
        seen.add(case_id)
        normalized.append(
            {
                "case_id": case_id,
                "expected_shared_cooling": label["expected_shared_cooling"],
                "first_isolated_threshold_index": threshold,
            }
        )
    if seen != planned_ids or len(normalized) != manifest["result_count"]:
        raise ValueError("LabelJoinEveryFrozenCaseRequired")
    normalized.sort(key=lambda item: item["case_id"])
    return normalized


def build_temperature_authenticated_label_join_statement(
    contract: Mapping[str, Any],
    manifest: Mapping[str, Any],
    labels: Sequence[Mapping[str, Any]],
    verifier: Any,
    *,
    prepared_at_utc: str,
    expires_at_utc: str,
    now_utc: str,
) -> bytes:
    """Bind every frozen prediction to one operator-authenticated outcome."""

    _window(prepared_at_utc, expires_at_utc, now_utc)
    contract_digest, manifest_digest = _validate_inputs(contract, manifest)
    normalized = _normalize_labels(manifest, labels)
    fingerprint = _fingerprint(verifier)
    statement = {
        "schema": STATEMENT_SCHEMA,
        "namespace": NAMESPACE,
        "scope": SCOPE,
        "key_id": KEY_ID,
        "operator_key_fingerprint": fingerprint,
        "prepared_at_utc": prepared_at_utc,
        "expires_at_utc": expires_at_utc,
        "statistical_contract_sha256": contract_digest,
        "blinded_manifest_sha256": manifest_digest,
        "detector_contract_sha256": manifest["detector_contract_sha256"],
        "case_count": len(normalized),
        "labels_sha256": _sha256(normalized),
        "labels": normalized,
        "every_frozen_case_labeled_once": True,
        "case_exclusions": [],
        "threshold_changes": [],
        "single_evaluation_per_detector_contract": True,
        "label_statement": (
            "I confirm these outcomes cover every member of the exact frozen cohort "
            "for one statistical review only."
        ),
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


def export_temperature_authenticated_label_join_statement(
    contract: Mapping[str, Any],
    manifest: Mapping[str, Any],
    labels: Sequence[Mapping[str, Any]],
    verifier: Any,
    output_path: str | Path,
    *,
    prepared_at_utc: str,
    expires_at_utc: str,
    now_utc: str,
) -> dict[str, Any]:
    """Export only the public label statement; never accept or invoke a signer."""

    statement = b""
    created = False
    errors: list[str] = []
    path = Path(output_path)
    try:
        if not path.is_absolute() or path.exists() or path.is_symlink():
            raise ValueError("LabelJoinOutputUnavailable")
        statement = build_temperature_authenticated_label_join_statement(
            contract,
            manifest,
            labels,
            verifier,
            prepared_at_utc=prepared_at_utc,
            expires_at_utc=expires_at_utc,
            now_utc=now_utc,
        )
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
        )
        created = True
        try:
            view = memoryview(statement)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("LabelJoinWriteFailed")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except (FileExistsError, OSError, TypeError, ValueError) as error:
        errors.append(str(error) or error.__class__.__name__)
        if created:
            with suppress(OSError):
                path.unlink()
    ready = not errors
    return {
        "schema": SCHEMA,
        "status": STATUS_READY if ready else STATUS_HOLD,
        "statement_created": ready,
        "statement_sha256": _sha256(statement) if statement else None,
        "private_key_accepted": False,
        "signer_invoked": False,
        "score_committed": False,
        "field_validated": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "errors": errors,
    }


def _nearest_rank_p10(values: Sequence[int]) -> int:
    if not values:
        raise ValueError("LabelJoinLeadPopulationEmpty")
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.10 * len(ordered)) - 1)]


def _score(
    contract: Mapping[str, Any],
    manifest: Mapping[str, Any],
    labels: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    predictions = {item["case_id"]: item for item in manifest["results"]}
    tp = fp = tn = fn = 0
    lead_samples: list[int] = []
    abstentions = 0
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
    positive_count = tp + fn
    negative_count = tn + fp
    total = len(labels)
    policy = contract["policy"]
    sensitivity = (
        wilson_interval(tp, positive_count) if positive_count else (0.0, 1.0)
    )
    false_positive = (
        wilson_interval(fp, negative_count) if negative_count else (0.0, 1.0)
    )
    abstention = wilson_interval(abstentions, total)
    lead_median = float(median(lead_samples)) if lead_samples else None
    lead_p10 = _nearest_rank_p10(lead_samples) if lead_samples else None
    gates = {
        "minimum_positive_cases": positive_count
        >= int(policy["minimum_positive_cases"]),
        "minimum_negative_cases": negative_count
        >= int(policy["minimum_negative_cases"]),
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
        "positive_cases": positive_count,
        "negative_cases": negative_count,
        "true_positives": tp,
        "false_positives": fp,
        "true_negatives": tn,
        "false_negatives": fn,
        "abstentions": abstentions,
        "threshold_landmark_true_positives": len(lead_samples),
        "sensitivity_point": round(tp / positive_count, 6)
        if positive_count
        else None,
        "sensitivity_wilson_lower": round(sensitivity[0], 6),
        "false_positive_rate_point": round(fp / negative_count, 6)
        if negative_count
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


def _commit_once(registry: Path, key: str, receipt: Mapping[str, Any]) -> Path:
    if not registry.is_absolute() or registry.is_symlink():
        raise ValueError("LabelJoinRegistryUnavailable")
    info = registry.stat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o022
    ):
        raise ValueError("LabelJoinRegistryInvalid")
    final = registry / f"score-{key}.json"
    if final.exists() or final.is_symlink():
        raise ValueError("LabelJoinDetectorAlreadyScored")
    stage = registry / f".score-{key}-{os.getpid()}.tmp"
    payload = _canonical(receipt) + b"\n"
    descriptor = os.open(
        stage,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("LabelJoinReceiptWriteFailed")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        os.link(stage, final, follow_symlinks=False)
        directory_fd = os.open(registry, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except FileExistsError as error:
        raise ValueError("LabelJoinDetectorAlreadyScored") from error
    finally:
        with suppress(OSError):
            stage.unlink()
    return final


def evaluate_temperature_authenticated_label_join(
    contract: Mapping[str, Any],
    manifest: Mapping[str, Any],
    labels: Sequence[Mapping[str, Any]],
    verifier: Any,
    statement_path: str | Path,
    signature_path: str | Path | None,
    registry_directory: str | Path,
    *,
    prepared_at_utc: str,
    expires_at_utc: str,
    now_utc: str,
) -> dict[str, Any]:
    """Authenticate, score, and atomically publish one immutable score receipt."""

    errors: list[str] = []
    signature_verified = False
    score_committed = False
    statement = b""
    statement_data: dict[str, Any] = {}
    score: dict[str, Any] = {}
    receipt: dict[str, Any] = {}
    receipt_path: Path | None = None
    try:
        statement = build_temperature_authenticated_label_join_statement(
            contract,
            manifest,
            labels,
            verifier,
            prepared_at_utc=prepared_at_utc,
            expires_at_utc=expires_at_utc,
            now_utc=now_utc,
        )
        statement_data = json.loads(statement)
        if _snapshot(Path(statement_path), MAX_PUBLIC_BYTES) != statement:
            raise ValueError("LabelJoinStatementMismatch")
        if signature_path is None:
            raise ValueError("LabelJoinSignatureRequired")
        signature = _snapshot(Path(signature_path), MAX_SIGNATURE_BYTES).decode(
            "ascii"
        )
        signature_verified = verifier(KEY_ID, statement, signature) is True
        if not signature_verified:
            raise ValueError("LabelJoinSignatureNotAuthenticated")
        score = _score(contract, manifest, statement_data["labels"])
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "status": STATUS_SCORED,
            "evaluated_at_utc": now_utc,
            "statistical_contract_sha256": statement_data[
                "statistical_contract_sha256"
            ],
            "blinded_manifest_sha256": statement_data["blinded_manifest_sha256"],
            "detector_contract_sha256": statement_data[
                "detector_contract_sha256"
            ],
            "label_statement_sha256": _sha256(statement),
            "label_signature_sha256": _sha256(signature.encode("ascii")),
            "labels_sha256": statement_data["labels_sha256"],
            "operator_key_fingerprint": statement_data[
                "operator_key_fingerprint"
            ],
            "score": score,
            "single_evaluation_per_detector_contract": True,
            "case_exclusions": [],
            "threshold_changes": [],
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
        receipt["receipt_sha256"] = _sha256(receipt)
        receipt_path = _commit_once(
            Path(registry_directory),
            statement_data["detector_contract_sha256"],
            receipt,
        )
        score_committed = True
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        OSError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
    ) as error:
        errors.append(str(error) or error.__class__.__name__)
    scored = not errors and signature_verified and score_committed
    return {
        "schema": SCHEMA,
        "status": STATUS_SCORED if scored else STATUS_HOLD,
        "namespace": NAMESPACE,
        "scope": SCOPE,
        "key_id": KEY_ID,
        "label_signature_verified": signature_verified,
        "every_frozen_case_labeled_once": scored,
        "score_committed": score_committed,
        "receipt_sha256": receipt.get("receipt_sha256") if scored else None,
        "receipt_filename": receipt_path.name if receipt_path else None,
        "score": score if scored else None,
        "statistical_gates_passed": score.get("statistical_gates_passed")
        if scored
        else False,
        "eligible_for_independent_score_review": scored,
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


def pending_temperature_authenticated_label_join(
    blinded_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Expose the next honest gate without inventing labels, signatures, or scores."""

    manifest_ready = (
        blinded_manifest.get("status") == STATUS_MANIFEST_READY
        and blinded_manifest.get("ready_for_authenticated_label_join") is True
    )
    return {
        "schema": SCHEMA,
        "status": STATUS_REQUIRED if manifest_ready else STATUS_HOLD,
        "blinded_manifest_ready": manifest_ready,
        "labels_present": False,
        "label_signature_verified": False,
        "score_committed": False,
        "statistical_gates_passed": False,
        "eligible_for_independent_score_review": False,
        "field_validated": False,
        "candidate_accepted": False,
        "candidate_installed": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "next_action": (
            "freeze the complete blinded cohort before labels are revealed"
            if not manifest_ready
            else "authenticate every frozen outcome, then commit exactly one score receipt"
        ),
        "errors": [] if manifest_ready else ["frozen blinded cohort required"],
    }


__all__ = [
    "NAMESPACE",
    "RECEIPT_SCHEMA",
    "SCHEMA",
    "STATEMENT_SCHEMA",
    "STATUS_HOLD",
    "STATUS_READY",
    "STATUS_SCORED",
    "build_temperature_authenticated_label_join_statement",
    "evaluate_temperature_authenticated_label_join",
    "export_temperature_authenticated_label_join_statement",
    "pending_temperature_authenticated_label_join",
]
