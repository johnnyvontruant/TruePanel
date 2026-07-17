"""
Storage health service.

Combines stable StorageInventory identity with changing SMART telemetry.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from .telemetry import (
    HealthState,
    StorageHealthRecord,
    StorageTelemetry,
)


class TelemetryProvider(Protocol):
    def collect(self, device: str) -> StorageTelemetry:
        ...


class InventoryProvider(Protocol):
    def devices(self) -> Iterable[object]:
        ...


class StorageHealthService:
    """Resolve current health for every inventoried storage device."""

    def __init__(
        self,
        inventory: InventoryProvider,
        provider: TelemetryProvider,
        *,
        warning_temperature_c: int = 45,
        critical_temperature_c: int = 55,
        nvme_warning_percentage_used: int = 80,
        nvme_critical_percentage_used: int = 95,
    ) -> None:
        if critical_temperature_c <= warning_temperature_c:
            raise ValueError(
                "critical temperature must exceed warning temperature"
            )

        self.inventory = inventory
        self.provider = provider
        self.warning_temperature_c = warning_temperature_c
        self.critical_temperature_c = critical_temperature_c
        self.nvme_warning_percentage_used = nvme_warning_percentage_used
        self.nvme_critical_percentage_used = nvme_critical_percentage_used

    def devices(self) -> list[StorageHealthRecord]:
        return [
            self._build_record(entry)
            for entry in self.inventory.devices()
        ]

    def find_device(
        self,
        device: str,
    ) -> StorageHealthRecord | None:
        name = device.removeprefix("/dev/")

        for record in self.devices():
            if record.device == name:
                return record

        return None

    def find_bay(
        self,
        physical_bay: int,
    ) -> StorageHealthRecord | None:
        for record in self.devices():
            if record.physical_bay == physical_bay:
                return record

        return None

    def by_state(
        self,
        state: HealthState | str,
    ) -> list[StorageHealthRecord]:
        target = HealthState(state)
        return [
            record
            for record in self.devices()
            if record.state is target
        ]

    def summary(self) -> dict[str, int]:
        records = self.devices()

        counts = {
            HealthState.HEALTHY.value: 0,
            HealthState.WARNING.value: 0,
            HealthState.CRITICAL.value: 0,
            HealthState.UNKNOWN.value: 0,
        }

        for record in records:
            counts[record.state.value] += 1

        counts["total"] = len(records)
        return counts

    def _build_record(self, entry: object) -> StorageHealthRecord:
        drive = getattr(entry, "drive")
        telemetry = self.provider.collect(drive.device)
        state, message = self.classify(telemetry)

        return StorageHealthRecord(
            device=drive.device,
            label=str(getattr(entry, "label", drive.device)),
            category=str(getattr(entry, "category", "unassigned")),
            physical_bay=getattr(entry, "physical_bay", None),
            serial=str(getattr(drive, "serial", "")),
            model=str(getattr(drive, "model", "")),
            transport=str(getattr(drive, "transport", "unknown")),
            telemetry=telemetry,
            state=state,
            message=message,
        )

    def classify(
        self,
        telemetry: StorageTelemetry,
    ) -> tuple[HealthState, str]:
        if telemetry.smart_passed is False:
            return HealthState.CRITICAL, "SMART self-assessment failed"

        critical_counters = {
            "pending sectors": telemetry.pending_sectors,
            "offline uncorrectable": telemetry.offline_uncorrectable,
        }

        for label, value in critical_counters.items():
            if value is not None and value > 0:
                return HealthState.CRITICAL, f"{label}: {value}"

        if (
            telemetry.temperature_c is not None
            and telemetry.temperature_c >= self.critical_temperature_c
        ):
            return (
                HealthState.CRITICAL,
                f"temperature {telemetry.temperature_c}°C",
            )

        if (
            telemetry.percentage_used is not None
            and telemetry.percentage_used
            >= self.nvme_critical_percentage_used
        ):
            return (
                HealthState.CRITICAL,
                f"NVMe endurance used: {telemetry.percentage_used}%",
            )

        warning_counters = {
            "reallocated sectors": telemetry.reallocated_sectors,
            "interface errors": telemetry.interface_errors,
        }

        for label, value in warning_counters.items():
            if value is not None and value > 0:
                return HealthState.WARNING, f"{label}: {value}"

        if (
            telemetry.temperature_c is not None
            and telemetry.temperature_c >= self.warning_temperature_c
        ):
            return (
                HealthState.WARNING,
                f"temperature {telemetry.temperature_c}°C",
            )

        if (
            telemetry.percentage_used is not None
            and telemetry.percentage_used
            >= self.nvme_warning_percentage_used
        ):
            return (
                HealthState.WARNING,
                f"NVMe endurance used: {telemetry.percentage_used}%",
            )

        has_measurement = any(
            value is not None
            for value in (
                telemetry.temperature_c,
                telemetry.smart_passed,
                telemetry.power_on_hours,
                telemetry.reallocated_sectors,
                telemetry.pending_sectors,
                telemetry.offline_uncorrectable,
                telemetry.interface_errors,
                telemetry.percentage_used,
                telemetry.available_spare,
            )
        )

        if not has_measurement:
            return (
                HealthState.UNKNOWN,
                telemetry.message or "no health telemetry available",
            )

        return HealthState.HEALTHY, "healthy"


__all__ = [
    "StorageHealthService",
    "TelemetryProvider",
]
