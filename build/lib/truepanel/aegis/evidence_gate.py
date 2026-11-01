"""Conservative evidence-admission and calibration-promotion gates for AEGIS."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EvidencePromotionPolicy:
    """Explicit statistical and diversity floors for field evidence."""

    confidence_z: float = 1.959963984540054
    max_false_positive_rate_upper: float = 0.01
    min_recall_lower: float = 0.80
    min_positive_recordings: int = 5
    min_negative_recordings: int = 20
    min_system_profiles: int = 2
    min_workload_classes: int = 4


DEFAULT_PROMOTION_POLICY = EvidencePromotionPolicy()


def builtin_lab_evidence_status() -> dict[str, Any]:
    """Return the deterministic built-in corpus's conservative gate status."""

    return evaluate_evidence_gate(
        {
            "confusion_matrix": {"true_positive": 1, "false_negative": 0},
            "negative_frame_count": 141,
            "false_positive_frame_count": 0,
        },
        {
            "source": "deterministic-synthetic",
            "privacy": "sanitized",
            "cases": [
                {"case_id": "fan-bearing-degradation", "expected_shared_cooling": True},
                *(
                    {
                        "case_id": f"adversarial-{index}",
                        "expected_shared_cooling": False,
                    }
                    for index in range(5)
                ),
            ],
        },
    )


def wilson_interval(
    successes: int,
    trials: int,
    *,
    z: float = DEFAULT_PROMOTION_POLICY.confidence_z,
) -> tuple[float, float]:
    """Return a Wilson score interval for one observed proportion."""

    successes = int(successes)
    trials = int(trials)
    if trials <= 0 or not 0 <= successes <= trials:
        raise ValueError(
            "Wilson interval requires 0 <= successes <= trials and trials > 0"
        )
    proportion = successes / trials
    z_squared = z * z
    denominator = 1 + z_squared / trials
    center = (proportion + z_squared / (2 * trials)) / denominator
    margin = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / trials + z_squared / (4 * trials * trials)
        )
        / denominator
    )
    return max(0.0, center - margin), min(1.0, center + margin)


def validate_field_manifest(manifest: dict[str, Any]) -> tuple[str, ...]:
    """Validate factual provenance fields without storing contributor identity."""

    errors = []
    if manifest.get("source") != "operator-opt-in-field":
        errors.append("source must be operator-opt-in-field")
    if manifest.get("privacy") != "sanitized":
        errors.append("privacy must be sanitized")
    card = manifest.get("dataset_card")
    if not isinstance(card, dict):
        return tuple(errors + ["dataset_card is required"])
    if card.get("collection_authority") != "operator-opt-in":
        errors.append("dataset_card.collection_authority must be operator-opt-in")
    if card.get("review_state") != "approved":
        errors.append("dataset_card.review_state must be approved")
    if card.get("raw_identifiers_retained") is not False:
        errors.append("dataset_card.raw_identifiers_retained must be false")
    if card.get("label_method") != "human-reviewed-incident-outcome":
        errors.append(
            "dataset_card.label_method must be human-reviewed-incident-outcome"
        )
    if "aegis-calibration" not in card.get("allowed_uses", ()):
        errors.append("dataset_card.allowed_uses must include aegis-calibration")
    if not str(card.get("retention_policy", "")).strip():
        errors.append("dataset_card.retention_policy is required")

    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        errors.append("field manifest requires labeled cases")
        return tuple(errors)
    for case in cases:
        case_id = str(case.get("case_id", "<unnamed>"))
        if not str(case.get("system_profile", "")).strip():
            errors.append(f"{case_id}: system_profile is required")
        if not str(case.get("workload_class", "")).strip():
            errors.append(f"{case_id}: workload_class is required")
        if case.get("incident_reviewed") is not True:
            errors.append(f"{case_id}: incident_reviewed must be true")
    return tuple(errors)


def evaluate_evidence_gate(
    report: dict[str, Any],
    manifest: dict[str, Any],
    *,
    policy: EvidencePromotionPolicy = DEFAULT_PROMOTION_POLICY,
) -> dict[str, Any]:
    """Measure eligibility while retaining an explicit human release gate."""

    matrix = report.get("confusion_matrix", {})
    true_positive = int(matrix.get("true_positive", 0))
    false_negative = int(matrix.get("false_negative", 0))
    false_positive_frames = int(report.get("false_positive_frame_count", 0))
    negative_frames = int(report.get("negative_frame_count", 0))
    recall_trials = true_positive + false_negative

    fpr_interval = (
        wilson_interval(false_positive_frames, negative_frames, z=policy.confidence_z)
        if negative_frames
        else (0.0, 1.0)
    )
    recall_interval = (
        wilson_interval(true_positive, recall_trials, z=policy.confidence_z)
        if recall_trials
        else (0.0, 1.0)
    )
    cases = manifest.get("cases") if isinstance(manifest.get("cases"), list) else []
    positives = sum(bool(case.get("expected_shared_cooling")) for case in cases)
    negatives = len(cases) - positives
    system_profiles = {str(case.get("system_profile", "")) for case in cases} - {""}
    workload_classes = {str(case.get("workload_class", "")) for case in cases} - {""}

    gaps = list(validate_field_manifest(manifest))
    checks = (
        (
            positives >= policy.min_positive_recordings,
            "positive recording floor not met",
        ),
        (
            negatives >= policy.min_negative_recordings,
            "negative recording floor not met",
        ),
        (
            len(system_profiles) >= policy.min_system_profiles,
            "system-profile diversity floor not met",
        ),
        (
            len(workload_classes) >= policy.min_workload_classes,
            "workload diversity floor not met",
        ),
        (
            fpr_interval[1] <= policy.max_false_positive_rate_upper,
            "false-positive upper confidence bound exceeds policy",
        ),
        (
            recall_interval[0] >= policy.min_recall_lower,
            "recall lower confidence bound is below policy",
        ),
    )
    gaps.extend(message for passed, message in checks if not passed)
    eligible = not gaps
    stage = "field_candidate" if eligible else "lab_calibrated"
    return {
        "schema_version": 1,
        "gate_id": "aegis-field-evidence-gate-v1",
        "stage": stage,
        "eligible_for_field_validation": eligible,
        "production_validated": False,
        "release_review_required": True,
        "confidence_level": 0.95,
        "measurements": {
            "false_positive_frames": false_positive_frames,
            "negative_frames": negative_frames,
            "false_positive_rate": round(
                false_positive_frames / negative_frames if negative_frames else 0.0, 6
            ),
            "false_positive_rate_wilson_upper": round(fpr_interval[1], 6),
            "true_positive_recordings": true_positive,
            "positive_recordings": recall_trials,
            "recall": round(true_positive / recall_trials if recall_trials else 0.0, 6),
            "recall_wilson_lower": round(recall_interval[0], 6),
            "system_profiles": len(system_profiles),
            "workload_classes": len(workload_classes),
        },
        "policy": {
            "max_false_positive_rate_upper": policy.max_false_positive_rate_upper,
            "min_recall_lower": policy.min_recall_lower,
            "min_positive_recordings": policy.min_positive_recordings,
            "min_negative_recordings": policy.min_negative_recordings,
            "min_system_profiles": policy.min_system_profiles,
            "min_workload_classes": policy.min_workload_classes,
        },
        "gaps": gaps,
        "authority": "evidence_assessment_only",
        "control_authority": False,
    }


__all__ = [
    "DEFAULT_PROMOTION_POLICY",
    "EvidencePromotionPolicy",
    "builtin_lab_evidence_status",
    "evaluate_evidence_gate",
    "validate_field_manifest",
    "wilson_interval",
]
