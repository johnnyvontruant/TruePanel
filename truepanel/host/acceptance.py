"""Passive clean-install acceptance reporting for the Host boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .fan_safety import HostFanSafetyReport
from .readiness import HostReadinessReport


@dataclass(frozen=True)
class HostAcceptanceReport:
    """Aggregate the fail-closed Host checks used by clean-install validation."""

    readiness: HostReadinessReport
    fan_safety: HostFanSafetyReport

    @property
    def accepted(self) -> bool:
        return (
            self.readiness.prepared_safely
            and self.fan_safety.safe
        )

    @property
    def activation_state(self) -> str:
        return self.readiness.activation_state

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "accepted": self.accepted,
            "activation_state": self.activation_state,
            "readiness": self.readiness.to_dict(),
            "fan_safety": self.fan_safety.to_dict(),
        }


def build_host_acceptance_report(
    readiness: HostReadinessReport,
    fan_safety: HostFanSafetyReport,
) -> HostAcceptanceReport:
    """Build a passive acceptance report from already-collected Host checks."""

    return HostAcceptanceReport(
        readiness=readiness,
        fan_safety=fan_safety,
    )


def format_host_acceptance_report(
    report: HostAcceptanceReport,
) -> str:
    """Format an operator-friendly clean-install Host acceptance summary."""

    readiness_state = (
        "PASS"
        if report.readiness.prepared_safely
        else "REVIEW"
    )
    fan_state = (
        "PASS"
        if report.fan_safety.safe
        else "REVIEW"
    )

    lines = [
        "TruePanel Host Acceptance",
        "=========================",
        "",
        (
            f"[{readiness_state}] Dormant Host readiness: "
            + (
                "PREPARED SAFELY"
                if report.readiness.prepared_safely
                else "REVIEW"
            )
        ),
        (
            f"[{fan_state}] Motherboard fan control: "
            + (
                "AUTOMATIC"
                if report.fan_safety.safe
                else "REVIEW"
            )
        ),
        (
            "Standalone activation: "
            f"{report.activation_state.upper()}"
        ),
        "",
        (
            "Host acceptance: PASS"
            if report.accepted
            else "Host acceptance: REVIEW"
        ),
    ]

    return "\n".join(lines)


__all__ = [
    "HostAcceptanceReport",
    "build_host_acceptance_report",
    "format_host_acceptance_report",
]
