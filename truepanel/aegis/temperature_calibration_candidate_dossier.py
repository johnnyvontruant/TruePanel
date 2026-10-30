"""Read-only, content-addressed dossier for a calibration candidate review."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from .temperature_calibration_decision import (
    DECISION_ACCEPT,
    MAX_PUBLIC_BYTES,
    _canonical,
    _sha256,
    _snapshot,
    verify_recorded_temperature_calibration_decision,
)

SCHEMA: Final = "truepanel.aegis-temperature-calibration-candidate-dossier/v1"
STATUS_READY: Final = "READY_FOR_MANUAL_CALIBRATION_CANDIDATE_REVIEW"
STATUS_HOLD: Final = "HOLD"

_DENIED = (
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


def _document(
    path: str | Path, *, require_canonical: bool = True
) -> tuple[dict[str, Any], bytes]:
    payload = _snapshot(Path(path), MAX_PUBLIC_BYTES)
    value = json.loads(payload)
    if not isinstance(value, dict) or (
        require_canonical and payload != _canonical(value) + b"\n"
    ):
        raise ValueError("CalibrationCandidateDossierDocumentInvalid")
    return value, payload


def assemble_temperature_calibration_candidate_dossier(
    review_receipt_path: str | Path,
    score_receipt_path: str | Path,
    decision_statement_path: str | Path,
    decision_signature_path: str | Path,
    decision_receipt_path: str | Path,
    verifier: Any,
    coverage_matrix: Mapping[str, Any],
    holodeck_evidence_path: str | Path,
    output_path: str | Path,
    *,
    now_utc: str,
) -> dict[str, Any]:
    """Assemble one immutable dossier after independently checking every link."""
    errors: list[str] = []
    dossier: dict[str, Any] = {}
    created = False
    try:
        decision = verify_recorded_temperature_calibration_decision(
            review_receipt_path,
            verifier,
            decision_statement_path,
            decision_signature_path,
            decision_receipt_path,
            now_utc=now_utc,
        )
        if decision["decision"] != DECISION_ACCEPT:
            raise ValueError("CalibrationCandidateDossierDecisionNotAccepted")
        review, review_bytes = _document(review_receipt_path)
        score, score_bytes = _document(score_receipt_path)
        evidence, evidence_bytes = _document(
            holodeck_evidence_path, require_canonical=False
        )
        unsigned_score = dict(score)
        score_digest = unsigned_score.pop("receipt_sha256", None)
        if score_digest != _sha256(unsigned_score):
            raise ValueError("CalibrationCandidateDossierScoreDigestMismatch")
        if review["score_receipt_sha256"] != score_digest:
            raise ValueError("CalibrationCandidateDossierScoreSubjectMismatch")
        if score.get("detector_contract_sha256") != review["detector_contract_sha256"]:
            raise ValueError("CalibrationCandidateDossierDetectorSubjectMismatch")
        if not (
            coverage_matrix.get("read_only") is True
            and coverage_matrix.get("total") == 8
            and coverage_matrix.get("trusted") == 8
            and coverage_matrix.get("gaps") == 0
            and coverage_matrix.get("contract_errors") == []
            and all(
                item.get("coverage_state") == "TRUSTED"
                for item in coverage_matrix.get("entries", [])
            )
        ):
            raise ValueError("CalibrationCandidateDossierCoverageIncomplete")
        measurements = evidence.get("measurements", {})
        if not (
            evidence.get("simulation") is True
            and evidence.get("hardware_isolated") is True
            and measurements.get("passing_accepts") == 1
            and measurements.get("failing_accepts") == 0
            and measurements.get("lead_samples") == 27
            and measurements.get("unsafe_ready_count") == 0
            and all(
                measurements.get(key) == 0
                for key in (
                    "field_validations",
                    "candidate_acceptances",
                    "candidate_installations",
                    "deployments",
                    "hardware_actions",
                    "automatic_promotions",
                )
            )
        ):
            raise ValueError("CalibrationCandidateDossierHoloDeckEvidenceInvalid")
        subjects = {
            "decision_receipt_sha256": decision["receipt_sha256"],
            "review_receipt_sha256": review["review_receipt_sha256"],
            "score_receipt_sha256": score_digest,
            "score_sha256": review["score_sha256"],
            "detector_contract_sha256": review["detector_contract_sha256"],
            "recovery_coverage_matrix_sha256": _sha256(coverage_matrix),
            "holodeck_evidence_sha256": hashlib.sha256(evidence_bytes).hexdigest(),
        }
        dossier = {
            "schema": SCHEMA,
            "status": STATUS_READY,
            "assembled_at_utc": now_utc,
            "decision": decision["decision"],
            "subjects": subjects,
            "coverage": {"total": 8, "trusted": 8, "gaps": 0},
            "proof": {"lead_samples": 27, "passing_accepts": 1, "failing_accepts": 0},
            "limitations": [
                "development evidence only",
                "manual review required",
                "no field validation",
            ],
            **{key: False for key in _DENIED},
        }
        dossier["dossier_sha256"] = _sha256(dossier)
        destination = Path(output_path)
        if not destination.is_absolute() or destination.exists():
            raise ValueError("CalibrationCandidateDossierOutputUnavailable")
        descriptor = os.open(
            destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600
        )
        try:
            payload = _canonical(dossier) + b"\n"
            written = 0
            while written < len(payload):
                written += os.write(descriptor, payload[written:])
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        created = True
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
        "status": STATUS_READY if created else STATUS_HOLD,
        "dossier_created": created,
        "dossier_sha256": dossier.get("dossier_sha256") if created else None,
        "candidate_review_ready": created,
        "candidate_accepted": False,
        "candidate_installed": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "automatic_promotion": False,
        "errors": errors,
    }


def pending_temperature_calibration_candidate_dossier(
    decision: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "status": STATUS_HOLD,
        "authenticated_decision_present": decision.get("operator_decision_present")
        is True,
        "candidate_review_ready": False,
        "candidate_accepted": False,
        "candidate_installed": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "automatic_promotion": False,
        "next_action": "Assemble and independently verify the exact read-only candidate dossier.",
    }


__all__ = [
    "SCHEMA",
    "STATUS_HOLD",
    "STATUS_READY",
    "assemble_temperature_calibration_candidate_dossier",
    "pending_temperature_calibration_candidate_dossier",
]
