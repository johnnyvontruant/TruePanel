"""
TruePanel compatibility survey result models.

These models describe passive compatibility observations only. They grant no
hardware-control authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class CompatibilityCheck:
    """One passive compatibility observation."""

    status: str
    name: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class CompatibilityReport:
    """Complete passive compatibility survey."""

    classification: str
    installation_mode: str
    hardware_control: str
    checks: tuple[CompatibilityCheck, ...]

    def to_dict(self) -> dict:
        return {
            "classification": self.classification,
            "installation_mode": self.installation_mode,
            "hardware_control": self.hardware_control,
            "checks": [
                check.to_dict()
                for check in self.checks
            ],
        }
