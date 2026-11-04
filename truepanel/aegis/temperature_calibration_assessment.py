"""Read-only characterization of an authenticated temperature corpus."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from .ssh_verifier import MAX_SIGNATURE_BYTES
from .temperature_authenticated_acceptance import KEY_ID
from .temperature_calibration_admission import (
    MAX_PUBLIC_BYTES,
    NAMESPACE,
    _snapshot,
)
from .temperature_calibration_corpus import _canonical, _case_receipts, _safe_root

SCHEMA: Final = "truepanel.aegis-temperature-calibration-corpus-assessment/v1"
STATUS_READY: Final = "CALIBRATION_CORPUS_CHARACTERIZED_FOR_INDEPENDENT_REVIEW"
STATUS_HOLD: Final = "HOLD"
MIN_CASES: Final = 4
MIN_POSITIVE: Final = 2
MIN_NEGATIVE: Final = 2
MIN_PROFILES: Final = 2
MIN_WORKLOADS: Final = 2


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _fail(name: str) -> None:
    raise ValueError(name)


def assess_temperature_calibration_corpus(
    corpus_path: str | Path,
    corpus_id: str,
    admission_verifier: Any,
) -> dict[str, Any]:
    """Authenticate every case and report corpus sufficiency without validation."""

    errors: list[str] = []
    cases: list[dict[str, Any]] = []
    snapshot_sha256: str | None = None
    try:
        root_path = Path(corpus_path)
        if not root_path.exists():
            _fail("CalibrationAssessmentCorpusMissing")
        if (
            getattr(admission_verifier, "namespace", None) != NAMESPACE
            or getattr(admission_verifier, "expected_key_ids", None) != (KEY_ID,)
        ):
            _fail("CalibrationAssessmentVerifierPolicyMismatch")
        root, _ = _safe_root(root_path, corpus_id)
        lock_descriptor = os.open(
            root / ".import.lock",
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
        )
        try:
            fcntl.flock(lock_descriptor, fcntl.LOCK_SH)
            receipts = _case_receipts(root / "cases")
            for receipt in receipts:
                case = root / "cases" / receipt["case_id"]
                statement = _snapshot(
                    case / "admission-statement.json", MAX_PUBLIC_BYTES
                )
                signature_bytes = _snapshot(
                    case / "admission-signature.sshsig", MAX_SIGNATURE_BYTES
                )
                try:
                    signature = signature_bytes.decode("ascii")
                    statement_data = json.loads(statement)
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise ValueError("CalibrationAssessmentArtifactInvalid") from error
                if admission_verifier(KEY_ID, statement, signature) is not True:
                    _fail("CalibrationAssessmentSignatureNotAuthenticated")
                labels = statement_data.get("labels")
                if (
                    not isinstance(labels, dict)
                    or labels != receipt.get("labels")
                    or labels.get("corpus_id") != corpus_id
                    or labels.get("case_id") != receipt.get("case_id")
                    or statement_data.get("recording_sha256")
                    != receipt.get("recording_sha256")
                    or statement_data.get("recording_bytes")
                    != receipt.get("recording_bytes")
                    or statement_data.get("frame_count") != receipt.get("frame_count")
                ):
                    _fail("CalibrationAssessmentLineageMismatch")
                negative = (
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
                )
                if any(statement_data.get(name) is not False for name in negative):
                    _fail("CalibrationAssessmentAuthorityEscalation")
                cases.append(
                    {
                        "case_id": labels["case_id"],
                        "challenge": labels["challenge"],
                        "system_profile": labels["system_profile"],
                        "workload_class": labels["workload_class"],
                        "expected_shared_cooling": labels[
                            "expected_shared_cooling"
                        ],
                        "first_isolated_threshold_index": labels[
                            "first_isolated_threshold_index"
                        ],
                        "receipt_sha256": receipt["receipt_sha256"],
                    }
                )
            if receipts != _case_receipts(root / "cases"):
                _fail("CalibrationAssessmentCorpusChanged")
        finally:
            os.close(lock_descriptor)
        snapshot_sha256 = _sha256(
            _canonical(
                {
                    "corpus_id": corpus_id,
                    "receipt_sha256s": [item["receipt_sha256"] for item in cases],
                }
            )
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as error:
        errors.append(str(error) or error.__class__.__name__)

    positives = sum(item["expected_shared_cooling"] is True for item in cases)
    negatives = sum(item["expected_shared_cooling"] is False for item in cases)
    profiles = Counter(item["system_profile"] for item in cases)
    workloads = Counter(item["workload_class"] for item in cases)
    threshold_landmarks = sum(
        item["first_isolated_threshold_index"] is not None for item in cases
    )
    integrity_verified = bool(cases) and not errors
    gates = {
        "authenticated_case_floor": len(cases) >= MIN_CASES,
        "positive_outcome_floor": positives >= MIN_POSITIVE,
        "negative_outcome_floor": negatives >= MIN_NEGATIVE,
        "system_profile_diversity": len(profiles) >= MIN_PROFILES,
        "workload_diversity": len(workloads) >= MIN_WORKLOADS,
        "threshold_landmark_present": threshold_landmarks > 0,
    }
    ready = not errors and all(gates.values())
    if not errors and not ready:
        errors.extend(name for name, passed in gates.items() if not passed)
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS_READY if ready else STATUS_HOLD,
        "corpus_id": corpus_id,
        "corpus_snapshot_sha256": snapshot_sha256,
        "case_count": len(cases),
        "positive_cases": positives,
        "negative_cases": negatives,
        "system_profiles": dict(sorted(profiles.items())),
        "workload_classes": dict(sorted(workloads.items())),
        "threshold_landmark_cases": threshold_landmarks,
        "gates": gates,
        "all_admission_signatures_reverified": integrity_verified,
        "read_only_assessment": True,
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
    result["record_sha256"] = _sha256(_canonical(result))
    return result


def pending_temperature_calibration_assessment(
    corpus_import: Mapping[str, Any],
) -> dict[str, Any]:
    """Expose the honest live state before a governed corpus exists."""

    imported = corpus_import.get("corpus_write_performed") is True
    result = {
        "schema": SCHEMA,
        "status": "ACTION_REQUIRED_CALIBRATION_ASSESSMENT" if imported else STATUS_HOLD,
        "case_count": int(corpus_import.get("case_count") or 0),
        "all_admission_signatures_reverified": False,
        "read_only_assessment": True,
        "field_validated": False,
        "production_validated": False,
        "candidate_accepted": False,
        "candidate_installed": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "next_action": (
            "import authenticated calibration cases"
            if not imported
            else "characterize corpus diversity and uncertainty without validation"
        ),
        "errors": [] if imported else ["authenticated corpus import required"],
    }
    result["record_sha256"] = _sha256(_canonical(result))
    return result


__all__ = [
    "STATUS_HOLD",
    "STATUS_READY",
    "assess_temperature_calibration_corpus",
    "pending_temperature_calibration_assessment",
]
