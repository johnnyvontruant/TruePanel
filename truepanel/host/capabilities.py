"""
Canonical host capability manifest for TruePanel.

This module translates passive compatibility observations into a stable
machine-readable description of what the host appears capable of providing.

Capability discovery never grants authority to actuate hardware.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class HostCapability:
    """
    One passive host capability.

    available describes whether the required host interface was discovered.

    authorized describes whether TruePanel currently has permission to perform
    state-changing operations through that capability. Passive compatibility
    discovery never grants that permission.
    """

    available: bool
    authorized: bool = False
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HostAgentCapabilities:
    """
    Passive capability manifest for the TruePanel host.

    This object describes discovered interfaces only. It is not an execution
    policy and must never be treated as permission to actuate hardware.
    """

    platform: HostCapability
    lcd: HostCapability
    fan_telemetry: HostCapability
    fan_control: HostCapability
    enclosure: HostCapability

    @property
    def hardware_authority_granted(self) -> bool:
        return any(
            capability.authorized
            for capability in (
                self.lcd,
                self.fan_control,
                self.enclosure,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "host_agent": {
                "available": self.platform.available,
                "hardware_authority_granted": (
                    self.hardware_authority_granted
                ),
            },
            "capabilities": {
                "platform": self.platform.to_dict(),
                "lcd": self.lcd.to_dict(),
                "fan_telemetry": self.fan_telemetry.to_dict(),
                "fan_control": self.fan_control.to_dict(),
                "enclosure": self.enclosure.to_dict(),
            },
        }


def _check_by_name(report: Any, name: str) -> Any | None:
    for item in getattr(report, "checks", ()):
        if getattr(item, "name", None) == name:
            return item

    return None


def _capability_from_check(
    report: Any,
    name: str,
    *,
    authorized: bool = False,
) -> HostCapability:
    item = _check_by_name(report, name)

    if item is None:
        return HostCapability(
            available=False,
            authorized=False,
            detail=f"{name} compatibility result unavailable",
        )

    status = str(
        getattr(item, "status", "")
    ).strip().upper()

    return HostCapability(
        available=status == "PASS",
        authorized=bool(authorized and status == "PASS"),
        detail=str(
            getattr(item, "detail", "")
        ),
    )


def capabilities_from_compatibility(
    report: Any,
) -> HostAgentCapabilities:
    """
    Build the canonical host capability manifest from a passive survey.

    The resulting manifest intentionally grants no state-changing authority.
    Authorization belongs to the commissioning and runtime safety layers.
    """

    classification = str(
        getattr(report, "classification", "")
    ).strip().upper()

    platform = HostCapability(
        available=classification not in {
            "",
            "UNSUPPORTED",
        },
        authorized=False,
        detail=(
            f"Compatibility classification: "
            f"{classification or 'UNKNOWN'}"
        ),
    )

    return HostAgentCapabilities(
        platform=platform,
        lcd=_capability_from_check(
            report,
            "Front Panel Serial",
        ),
        fan_telemetry=_capability_from_check(
            report,
            "Fan Telemetry",
        ),
        fan_control=_capability_from_check(
            report,
            "PWM Interfaces",
        ),
        enclosure=_capability_from_check(
            report,
            "Enclosure Topology",
        ),
    )


__all__ = [
    "HostAgentCapabilities",
    "HostCapability",
    "capabilities_from_compatibility",
]
