"""Bounded, model-free drive-health evidence for WINGMAN offline briefs.

Pool availability and per-drive health are distinct observations. The adapter
only repeats recognized status classifications and nonnegative published counts;
it cannot certify a drive, map an unknown bay, or authorize repair.
"""

from __future__ import annotations

from typing import Any

_ERROR_FIELDS = (
    ("reallocated", "reallocated"),
    ("pending", "pending"),
    ("offline_uncorrectable", "offline uncorrectable"),
    ("reported_uncorrect", "reported uncorrectable"),
    ("media_errors", "media errors"),
)
_CONCERN_STATES = frozenset({"critical", "warning", "failed"})
_MAX_COUNT = 999_999_999
_MAX_RECORDS = 16
_MAX_ISSUES = 8


def drive_health_evidence(
    storage: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Extract evidence of drive concerns from the composed public snapshot."""
    smart = storage.get("smart")
    if not isinstance(smart, list) or not smart:
        return [], ["Drive-health records are unavailable."]

    observations: list[dict[str, Any]] = []
    uncertainty: list[str] = []

    if len(smart) > _MAX_RECORDS:
        uncertainty.append("Additional drive-health records were not examined.")

    for record in smart[:_MAX_RECORDS]:
        if not isinstance(record, dict):
            uncertainty.append("A drive-health record was malformed.")
            continue

        state = record.get("health_state")
        recognized_state = (
            state.lower()
            if isinstance(state, str)
            and state.lower() in {"critical", "warning", "failed", "healthy"}
            else None
        )

        counts: list[str] = []
        positive_count = False
        for field, label in _ERROR_FIELDS:
            value = record.get(field)
            if isinstance(value, int) and not isinstance(value, bool):
                if 0 <= value <= _MAX_COUNT:
                    if value > 0:
                        positive_count = True
                        counts.append(f"{label}: {value:,}")
                else:
                    uncertainty.append("A drive error count was outside the supported range.")
            elif value is not None:
                uncertainty.append("A drive error count was not verified.")

        if recognized_state not in _CONCERN_STATES and not positive_count:
            continue

        bay = record.get("physical_bay")
        mapped = isinstance(bay, int) and not isinstance(bay, bool) and 1 <= bay <= 6
        name = f"Bay {bay}" if mapped else "Unmapped drive"
        if not mapped:
            uncertainty.append("An affected drive's physical bay was not verified.")

        if recognized_state in _CONCERN_STATES:
            finding = f"reported drive-health state {recognized_state.upper()}"
        elif recognized_state == "healthy":
            finding = "reported error counts despite drive-health state HEALTHY"
        else:
            finding = "reported nonzero drive error counts; health classification unavailable"

        overall = record.get("health")
        if isinstance(overall, str) and overall.upper() == "PASSED":
            finding += "; SMART overall PASSED does not clear this finding"

        if counts:
            finding += "; " + ", ".join(counts)

        observations.append(
            {"text": f"{name}: {finding}.", "source_ids": ["status:storage"]}
        )

        if len(observations) == _MAX_ISSUES:
            if len(smart) > _MAX_ISSUES:
                uncertainty.append("Additional drive-health findings may be omitted.")
            break

    return observations, list(dict.fromkeys(uncertainty))[:8]


__all__ = ["drive_health_evidence"]
