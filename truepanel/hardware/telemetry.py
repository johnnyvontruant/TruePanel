"""
TruePanel hardware telemetry models.

Telemetry records describe changing hardware state without modifying the
immutable storage inventory and topology models.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class HealthState(str, Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class StorageTelemetry:
    """
    Raw health telemetry for one storage device.

    Missing values remain None. Providers must not invent measurements when
    hardware, permissions, or utilities do not expose them.
    """

    device: str
    temperature_c: int | None = None
    smart_passed: bool | None = None
    power_on_hours: int | None = None
    reallocated_sectors: int | None = None
    pending_sectors: int | None = None
    offline_uncorrectable: int | None = None
    interface_errors: int | None = None
    percentage_used: int | None = None
    available_spare: int | None = None
    source: str = "unknown"
    message: str = ""
    collected_at: datetime | None = None

    @property
    def device_path(self) -> str:
        return f"/dev/{self.device}" if self.device else ""

    @property
    def timestamp(self) -> datetime:
        return self.collected_at or datetime.now(timezone.utc)


@dataclass(frozen=True)
class StorageHealthRecord:
    """Inventory identity combined with current telemetry and health state."""

    device: str
    label: str
    category: str
    physical_bay: int | None
    serial: str
    model: str
    transport: str
    telemetry: StorageTelemetry
    state: HealthState
    message: str

    @property
    def device_path(self) -> str:
        return f"/dev/{self.device}" if self.device else ""

    @property
    def temperature_c(self) -> int | None:
        return self.telemetry.temperature_c

    @property
    def smart_passed(self) -> bool | None:
        return self.telemetry.smart_passed

    @property
    def source(self) -> str:
        return self.telemetry.source


__all__ = [
    "HealthState",
    "StorageHealthRecord",
    "StorageTelemetry",
]
