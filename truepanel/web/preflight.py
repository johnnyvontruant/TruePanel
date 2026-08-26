"""Mission Control projection for passive compatibility preflight data."""

from __future__ import annotations

from truepanel.compatibility.models import CompatibilityCheck, CompatibilityReport

PREFLIGHT_SCHEMA_VERSION = 2

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


def _worst_status(checks: list[dict[str, object]]) -> str:
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


def _review_contract(check: CompatibilityCheck) -> dict[str, object]:
    """Explain how a non-PASS compatibility check can become machine PASS.

    Preflight remains evidence-driven. Operator review can explain or resolve
    the underlying condition, but it cannot repaint REVIEW as PASS without a
    subsequent compatibility run returning PASS.
    """

    status = str(check.status).strip().upper()
    detail = str(check.detail or "").strip()

    if status == "PASS":
        return {
            "state": "resolved",
            "review_required": False,
            "rerun_available": True,
            "machine_pass_required": True,
            "manual_pass_allowed": False,
            "reason": "Compatibility evidence currently passes.",
            "next_action": "No operator action required.",
        }

    if status == "FAIL":
        return {
            "state": "blocked",
            "review_required": True,
            "rerun_available": True,
            "machine_pass_required": True,
            "manual_pass_allowed": False,
            "reason": detail or "Compatibility evidence failed.",
            "next_action": (
                "Correct the reported incompatibility, then run Preflight "
                "again to obtain a machine-verified PASS."
            ),
        }

    return {
        "state": "reviewing",
        "review_required": True,
        "rerun_available": True,
        "machine_pass_required": True,
        "manual_pass_allowed": False,
        "reason": detail or "Compatibility evidence is incomplete or ambiguous.",
        "next_action": (
            "Review the reported evidence and resolve or verify the underlying "
            "condition, then run Preflight again. PASS is granted only when the "
            "compatibility check itself returns PASS."
        ),
    }


def build_preflight_payload(report: CompatibilityReport) -> dict:
    """Project a passive compatibility report into Mission Control UI data."""

    grouped: dict[str, list[dict[str, object]]] = {
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

        payload["review"] = _review_contract(check)
        grouped[_section_id(check)].append(payload)

    sections = []
    for section_id, label in _SECTION_ORDER:
        checks = grouped[section_id]
        status = _worst_status(checks)
        pending = [
            check
            for check in checks
            if str(check.get("status", "REVIEW")).upper() != "PASS"
        ]
        sections.append(
            {
                "id": section_id,
                "label": label,
                "status": status,
                "checks": checks,
                "review": {
                    "state": "resolved" if not pending else "reviewing",
                    "review_required": bool(pending),
                    "pending_checks": len(pending),
                    "rerun_available": True,
                    "machine_pass_required": True,
                    "manual_pass_allowed": False,
                },
            }
        )

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
        "recovery": {
            "state": "resolved" if flight_status == "READY" else "reviewing",
            "verification": "rerun_passive_compatibility_survey",
            "automated": True,
            "machine_pass_required": True,
            "manual_pass_allowed": False,
            "criteria": (
                "All required compatibility evidence must evaluate to PASS "
                "or the report classification must become SUPPORTED."
            ),
        },
    }


__all__ = [
    "PREFLIGHT_SCHEMA_VERSION",
    "build_preflight_payload",
]
