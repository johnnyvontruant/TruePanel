"""Mission Control projection for passive compatibility preflight data."""

from __future__ import annotations

from truepanel.compatibility.models import CompatibilityCheck, CompatibilityReport

PREFLIGHT_SCHEMA_VERSION = 1

_STATUS_RANK = {
    "PASS": 0,
    "REVIEW": 1,
    "FAIL": 2,
}

_SECTION_ORDER = (
    ("host", "Host"),
    ("storage", "Storage"),
    ("cooling", "Cooling"),
    ("front-panel", "Front Panel"),
    ("safety", "Safety Interlocks"),
)


def _section_id(check: CompatibilityCheck) -> str:
    name = check.name.strip().lower()

    if name == "front panel serial":
        return "front-panel"

    if name == "safety authority":
        return "safety"

    if (
        name.startswith("fan ")
        or "pwm" in name
        or "cooling" in name
    ):
        return "cooling"

    if (
        "storage" in name
        or "enclosure" in name
        or "nvme" in name
        or "boot media" in name
        or "zfs" in name
        or "front-bay" in name
    ):
        return "storage"

    return "host"


def _worst_status(checks: list[dict[str, str]]) -> str:
    if not checks:
        return "REVIEW"

    return max(
        (str(check.get("status", "REVIEW")).upper() for check in checks),
        key=lambda status: _STATUS_RANK.get(status, _STATUS_RANK["REVIEW"]),
    )


def _flight_status(classification: str) -> str:
    normalized = str(classification).strip().upper()

    if normalized == "SUPPORTED":
        return "READY"

    if normalized == "UNSUPPORTED":
        return "HOLD"

    return "REVIEW"


def _summary(flight_status: str) -> str:
    if flight_status == "READY":
        return "Required TruePanel compatibility signals are ready."

    if flight_status == "HOLD":
        return "A required compatibility signal is unsupported."

    return "One or more compatibility signals need operator review."


def build_preflight_payload(report: CompatibilityReport) -> dict:
    """Project a passive compatibility report into Mission Control UI data."""

    grouped: dict[str, list[dict[str, str]]] = {
        section_id: []
        for section_id, _label in _SECTION_ORDER
    }

    counts = {
        "pass": 0,
        "review": 0,
        "fail": 0,
    }

    for check in report.checks:
        payload = check.to_dict()
        status = str(check.status).strip().lower()

        if status in counts:
            counts[status] += 1

        grouped[_section_id(check)].append(payload)

    sections = [
        {
            "id": section_id,
            "label": label,
            "status": _worst_status(grouped[section_id]),
            "checks": grouped[section_id],
        }
        for section_id, label in _SECTION_ORDER
    ]

    flight_status = _flight_status(report.classification)

    return {
        "schema_version": PREFLIGHT_SCHEMA_VERSION,
        "read_only": True,
        "flight_status": flight_status,
        "classification": report.classification,
        "installation_mode": report.installation_mode,
        "hardware_control": report.hardware_control,
        "summary": _summary(flight_status),
        "counts": counts,
        "sections": sections,
    }


__all__ = [
    "PREFLIGHT_SCHEMA_VERSION",
    "build_preflight_payload",
]
