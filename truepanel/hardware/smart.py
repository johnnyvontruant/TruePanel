"""
Read-only smartctl telemetry provider.

The provider invokes smartctl using JSON output and normalizes ATA, SCSI, USB,
and NVMe responses into StorageTelemetry records.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .telemetry import StorageTelemetry


CommandRunner = Callable[..., subprocess.CompletedProcess]


def _nested(data: Mapping[str, Any], *keys: str) -> Any:
    value: Any = data

    for key in keys:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)

    return value


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return int(value)

    if isinstance(value, str):
        try:
            return int(float(value.strip()))
        except ValueError:
            return None

    return None


def _smart_passed(data: Mapping[str, Any]) -> bool | None:
    passed = _nested(data, "smart_status", "passed")

    if isinstance(passed, bool):
        return passed

    return None


def _temperature(data: Mapping[str, Any]) -> int | None:
    candidates = (
        _nested(data, "temperature", "current"),
        _nested(data, "nvme_smart_health_information_log", "temperature"),
        _nested(data, "scsi_temperature", "current"),
    )

    for value in candidates:
        parsed = _integer(value)
        if parsed is not None:
            return parsed

    return None


def _ata_attribute(
    data: Mapping[str, Any],
    *names: str,
) -> int | None:
    table = _nested(data, "ata_smart_attributes", "table")

    if not isinstance(table, list):
        return None

    normalized_names = {
        name.lower().replace(" ", "_")
        for name in names
    }

    for attribute in table:
        if not isinstance(attribute, Mapping):
            continue

        name = str(attribute.get("name", "")).lower().replace(" ", "_")

        if name not in normalized_names:
            continue

        raw = attribute.get("raw")

        if isinstance(raw, Mapping):
            value = _integer(raw.get("value"))
            if value is not None:
                return value

        value = _integer(raw)
        if value is not None:
            return value

    return None


def parse_smartctl_json(
    device: str,
    data: Mapping[str, Any],
    *,
    message: str = "",
) -> StorageTelemetry:
    """Normalize one decoded smartctl JSON response."""

    nvme = data.get("nvme_smart_health_information_log", {})
    if not isinstance(nvme, Mapping):
        nvme = {}

    power_on_hours = _integer(
        _nested(data, "power_on_time", "hours")
    )

    if power_on_hours is None:
        power_on_hours = _integer(nvme.get("power_on_hours"))

    interface_errors = _integer(
        _nested(data, "sata_phy_event_counters", "table", 0)
    )

    if interface_errors is None:
        interface_errors = _ata_attribute(
            data,
            "UDMA_CRC_Error_Count",
            "Interface_CRC_Error_Count",
        )

    return StorageTelemetry(
        device=Path(device).name,
        temperature_c=_temperature(data),
        smart_passed=_smart_passed(data),
        power_on_hours=power_on_hours,
        reallocated_sectors=_ata_attribute(
            data,
            "Reallocated_Sector_Ct",
            "Reallocated_Event_Count",
        ),
        pending_sectors=_ata_attribute(
            data,
            "Current_Pending_Sector",
        ),
        offline_uncorrectable=_ata_attribute(
            data,
            "Offline_Uncorrectable",
        ),
        interface_errors=interface_errors,
        percentage_used=_integer(nvme.get("percentage_used")),
        available_spare=_integer(nvme.get("available_spare")),
        source="smartctl",
        message=message,
        collected_at=datetime.now(timezone.utc),
    )


class SmartctlProvider:
    """
    Collect storage telemetry through smartctl.

    Failures are returned as unknown telemetry instead of raising into the
    inventory, CLI, or display stack.
    """

    def __init__(
        self,
        *,
        executable: str = "smartctl",
        timeout: float = 10.0,
        runner: CommandRunner | None = None,
    ) -> None:
        self.executable = executable
        self.timeout = timeout
        self.runner = runner or subprocess.run

    def collect(self, device: str) -> StorageTelemetry:
        name = Path(device).name
        path = f"/dev/{name}"

        try:
            result = self.runner(
                [
                    self.executable,
                    "--json",
                    "--all",
                    path,
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except FileNotFoundError:
            return StorageTelemetry(
                device=name,
                source="unavailable",
                message=f"{self.executable} is not installed",
            )
        except subprocess.TimeoutExpired:
            return StorageTelemetry(
                device=name,
                source="timeout",
                message=f"SMART query timed out after {self.timeout:g}s",
            )
        except (PermissionError, OSError) as exc:
            return StorageTelemetry(
                device=name,
                source="error",
                message=str(exc),
            )

        stdout = result.stdout.strip()

        if not stdout:
            message = result.stderr.strip() or (
                f"smartctl returned exit code {result.returncode}"
            )
            return StorageTelemetry(
                device=name,
                source="smartctl",
                message=message,
            )

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return StorageTelemetry(
                device=name,
                source="smartctl",
                message="smartctl returned invalid JSON",
            )

        if not isinstance(data, Mapping):
            return StorageTelemetry(
                device=name,
                source="smartctl",
                message="smartctl returned an unexpected JSON document",
            )

        message = result.stderr.strip()

        if result.returncode:
            smartctl_messages = data.get("smartctl", {}).get("messages", [])
            if isinstance(smartctl_messages, list):
                text = "; ".join(
                    str(item.get("string", ""))
                    for item in smartctl_messages
                    if isinstance(item, Mapping) and item.get("string")
                )
                message = text or message

        return parse_smartctl_json(
            name,
            data,
            message=message,
        )


__all__ = [
    "SmartctlProvider",
    "parse_smartctl_json",
]
