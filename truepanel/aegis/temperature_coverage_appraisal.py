"""Fail-closed appraisal for the unaccepted temperature coverage candidate."""

from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .temperature_coverage import (
    build_temperature_coverage_candidate,
    validate_temperature_coverage_candidate,
)

SCHEMA = "truepanel.aegis-temperature-coverage-appraisal/v1"
STATUS_READY = "READY_FOR_INDEPENDENT_REVIEW"
STATUS_HOLD = "HOLD"

# These subjects are the exact outputs reviewed on PR #202.  They are not
# acceptance metadata: changing any subject requires a new appraisal.
PINNED_SUBJECTS = {
    "accepted_matrix_sha256": "8b206f8bfa897eb454f53506301d50384db64ac8d1d2515eb02817f931d2ca98",
    "candidate_sha256": "b769ac21182c91cad36ff54c43d61a8e9ff7b1ec9c7f64fa29a48e3b4de458a9",
    "candidate_document_sha256": "495fba0a70f2ea07e07634cd8fc7678bc463b66af8ef461299c8ce5271376029",
    "holodeck_evidence_sha256": "1cf9806f0f908e5307938826627378ad9b14e1c83940753b2c89ef55cc8e2755",
    "holodeck_document_sha256": "508ee25670e2920ff6bed56dcbb202c059bad2904c70f959b9c5e427a3aa2c99",
    "implementation_sha256": "1baa85e3f6c6d73eb12ce0fbbcc1defc8c0794249b826de036fae385410dbf38",
}


def _sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _without(mapping: Mapping[str, Any], key: str) -> dict[str, Any]:
    result = deepcopy(dict(mapping))
    result.pop(key, None)
    return result


def temperature_coverage_implementation_sha256(checkride: Any) -> str:
    """Bind the builder, validator, and deterministic evidence producer."""

    source = "".join(
        inspect.getsource(function)
        for function in (
            build_temperature_coverage_candidate,
            validate_temperature_coverage_candidate,
            checkride,
            appraise_temperature_coverage,
        )
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def appraise_temperature_coverage(
    accepted_matrix: Mapping[str, Any],
    candidate: Mapping[str, Any],
    holodeck_report: Mapping[str, Any],
    *,
    implementation_sha256: str,
    pinned_subjects: Mapping[str, str] = PINNED_SUBJECTS,
) -> dict[str, Any]:
    """Independently reproduce and appraise the exact PR #202 subjects.

    READY means only that the immutable candidate is suitable for a separate
    human review.  It never accepts, installs, or authorizes the candidate.
    """

    accepted = deepcopy(dict(accepted_matrix))
    proposed = deepcopy(dict(candidate))
    evidence = deepcopy(dict(holodeck_report))
    pins = dict(pinned_subjects)
    errors: list[str] = []

    required_pins = set(PINNED_SUBJECTS)
    if set(pins) != required_pins:
        errors.append("pinned subject manifest has unknown or missing fields")

    subjects = {
        "accepted_matrix_sha256": _sha256(accepted),
        "candidate_sha256": str(proposed.get("candidate_sha256", "")),
        "candidate_document_sha256": _sha256(proposed),
        "holodeck_evidence_sha256": str(evidence.get("evidence_sha256", "")),
        "holodeck_document_sha256": _sha256(evidence),
        "implementation_sha256": str(implementation_sha256),
    }
    for name in sorted(required_pins):
        if subjects.get(name) != pins.get(name):
            errors.append(f"{name} does not match the reviewed subject")

    candidate_digest = _sha256(_without(proposed, "candidate_sha256"))
    if candidate_digest != proposed.get("candidate_sha256"):
        errors.append("candidate self-digest is invalid")
    evidence_digest = _sha256(_without(evidence, "evidence_sha256"))
    if evidence_digest != evidence.get("evidence_sha256"):
        errors.append("HoloDeck evidence self-digest is invalid")

    rehearsal = evidence.get("verification_rehearsal")
    if not isinstance(rehearsal, dict):
        errors.append("HoloDeck verification rehearsal is missing")
    else:
        reconstructed = build_temperature_coverage_candidate(accepted, rehearsal)
        if reconstructed != proposed:
            errors.append("candidate does not match independent reconstruction")

    errors.extend(validate_temperature_coverage_candidate(proposed))

    measurements = evidence.get("measurements")
    required_measurements = {
        "scenario_count": 5,
        "aegis_detection_sample": 1,
        "isolated_temperature_threshold_sample": None,
        "blind_spot_false_negatives_avoided": 1,
        "consolidated_incident_count": 1,
        "alert_reduction_percent": 50,
        "false_overheating_claims": 0,
        "cross_drive_false_correlations": 0,
        "runtime_writes": 0,
        "hardware_actions": 0,
    }
    if not isinstance(measurements, dict) or any(
        measurements.get(name) != value
        for name, value in required_measurements.items()
    ):
        errors.append("HoloDeck measurements do not satisfy the reviewed proof")
    if (
        evidence.get("simulation") is not True
        or evidence.get("hardware_isolated") is not True
        or evidence.get("production_mutation") is not False
        or evidence.get("control_authority") is not False
    ):
        errors.append("HoloDeck safety boundary is invalid")
    if (
        proposed.get("accepted") is not False
        or proposed.get("installed") is not False
        or proposed.get("automatic_acceptance") is not False
    ):
        errors.append("candidate authority boundary is invalid")

    unique_errors = list(dict.fromkeys(errors))
    result = {
        "schema": SCHEMA,
        "status": STATUS_HOLD if unique_errors else STATUS_READY,
        "ready_for_independent_review": not unique_errors,
        "accepted": False,
        "installed": False,
        "automatic_acceptance": False,
        "runtime_authority": False,
        "production_authority": False,
        "hardware_authority": False,
        "subjects": subjects,
        "errors": unique_errors,
        "coverage": {
            "accepted": "8/8 trusted",
            "candidate": "9/9 rehearsed",
            "candidate_gap_count": proposed.get("gaps"),
        },
    }
    result["appraisal_sha256"] = _sha256(result)
    return result


__all__ = [
    "PINNED_SUBJECTS",
    "SCHEMA",
    "STATUS_HOLD",
    "STATUS_READY",
    "appraise_temperature_coverage",
    "temperature_coverage_implementation_sha256",
]
