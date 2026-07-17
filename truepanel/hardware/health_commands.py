"""
Production CLI support for storage health telemetry.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from enum import Enum
from typing import Any

from .manager import HardwareManager
from .telemetry import HealthState, StorageHealthRecord


def register_health_command(hardware_subcommands) -> None:
    parser = hardware_subcommands.add_parser(
        "health",
        help="Show live storage health and SMART telemetry",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        dest="hardware_json",
        help="Emit machine-readable JSON",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        dest="hardware_verbose",
        help="Show detailed SMART telemetry",
    )

    selector = parser.add_mutually_exclusive_group()

    selector.add_argument(
        "--device",
        metavar="DEVICE",
        help="Show one device, such as sda or /dev/sda",
    )
    selector.add_argument(
        "--bay",
        type=int,
        metavar="NUMBER",
        help="Show one physical front-bay number",
    )
    selector.add_argument(
        "--state",
        choices=[state.value for state in HealthState],
        help="Show devices matching one health state",
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, dict):
        return {
            key: _json_value(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]

    return value


def health_record_to_dict(
    record: StorageHealthRecord,
) -> dict[str, Any]:
    payload = asdict(record)
    payload["device_path"] = record.device_path
    payload["temperature_c"] = record.temperature_c
    payload["smart_passed"] = record.smart_passed
    payload["source"] = record.source

    return _json_value(payload)


def build_health_report(
    manager: HardwareManager,
    *,
    device: str | None = None,
    bay: int | None = None,
    state: str | None = None,
) -> dict[str, Any]:
    service = manager.health

    if device:
        record = service.find_device(device)
        records = [record] if record is not None else []
    elif bay is not None:
        record = service.find_bay(bay)
        records = [record] if record is not None else []
    elif state:
        records = service.by_state(state)
    else:
        records = service.devices()

    counts = {
        HealthState.HEALTHY.value: 0,
        HealthState.WARNING.value: 0,
        HealthState.CRITICAL.value: 0,
        HealthState.UNKNOWN.value: 0,
    }

    for record in records:
        counts[record.state.value] += 1

    return {
        "device_count": len(records),
        "summary": {
            **counts,
            "total": len(records),
        },
        "filters": {
            "device": device,
            "bay": bay,
            "state": state,
        },
        "devices": [
            health_record_to_dict(record)
            for record in records
        ],
    }


def _temperature_text(record: StorageHealthRecord) -> str:
    if record.temperature_c is None:
        return "--°C"

    return f"{record.temperature_c}°C"


def _smart_text(record: StorageHealthRecord) -> str:
    if record.smart_passed is True:
        return "PASS"

    if record.smart_passed is False:
        return "FAIL"

    return "N/A"


def _state_label(state: HealthState) -> str:
    return {
        HealthState.HEALTHY: "HEALTHY",
        HealthState.WARNING: "WARNING",
        HealthState.CRITICAL: "CRITICAL",
        HealthState.UNKNOWN: "UNKNOWN",
    }[state]


def print_health_report(
    report: dict[str, Any],
    *,
    verbose: bool = False,
) -> None:
    summary = report["summary"]

    print()
    print("TruePanel Storage Health")
    print("------------------------")
    print(f"Devices  : {summary['total']}")
    print(f"Healthy  : {summary['healthy']}")
    print(f"Warning  : {summary['warning']}")
    print(f"Critical : {summary['critical']}")
    print(f"Unknown  : {summary['unknown']}")
    print()

    devices = report["devices"]

    if not devices:
        print("No matching storage devices.")
        return

    for payload in devices:
        telemetry = payload["telemetry"]
        state = str(payload["state"]).upper()
        temperature = payload["temperature_c"]
        temperature_text = (
            f"{temperature}°C"
            if temperature is not None
            else "--°C"
        )

        print(
            f"{payload['label']:<18} "
            f"{payload['device_path']:<14} "
            f"{temperature_text:<6} "
            f"{state:<8} "
            f"{payload['message']}"
        )

        if not verbose:
            continue

        print(f"  Model             : {payload['model'] or 'unknown'}")
        print(f"  Serial            : {payload['serial'] or 'unknown'}")
        print(f"  Category          : {payload['category']}")
        print(f"  Transport         : {payload['transport']}")
        print(
            "  Physical Bay      : "
            f"{payload['physical_bay'] if payload['physical_bay'] is not None else 'N/A'}"
        )
        print(
            "  SMART Assessment  : "
            f"{_smart_payload_text(payload['smart_passed'])}"
        )
        print(
            "  Power-On Hours    : "
            f"{_display_value(telemetry['power_on_hours'])}"
        )
        print(
            "  Reallocated       : "
            f"{_display_value(telemetry['reallocated_sectors'])}"
        )
        print(
            "  Pending           : "
            f"{_display_value(telemetry['pending_sectors'])}"
        )
        print(
            "  Offline Uncorrect.: "
            f"{_display_value(telemetry['offline_uncorrectable'])}"
        )
        print(
            "  Interface Errors  : "
            f"{_display_value(telemetry['interface_errors'])}"
        )
        print(
            "  NVMe Used         : "
            f"{_percentage_value(telemetry['percentage_used'])}"
        )
        print(
            "  Available Spare   : "
            f"{_percentage_value(telemetry['available_spare'])}"
        )
        print(f"  Source            : {payload['source']}")

        collected_at = telemetry.get("collected_at")
        if collected_at:
            print(f"  Collected         : {collected_at}")

        provider_message = telemetry.get("message")
        if provider_message:
            print(f"  Provider Message  : {provider_message}")

        print()


def _display_value(value: Any) -> str:
    return "N/A" if value is None else str(value)


def _percentage_value(value: Any) -> str:
    return "N/A" if value is None else f"{value}%"


def _smart_payload_text(value: bool | None) -> str:
    if value is True:
        return "PASS"

    if value is False:
        return "FAIL"

    return "N/A"


def handle_health_command(
    args,
    *,
    manager: HardwareManager,
    print_json=None,
) -> bool:
    if getattr(args, "hardware_action", None) != "health":
        return False

    report = build_health_report(
        manager,
        device=getattr(args, "device", None),
        bay=getattr(args, "bay", None),
        state=getattr(args, "state", None),
    )

    if getattr(args, "hardware_json", False):
        if print_json is not None:
            print_json(report)
        else:
            print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_health_report(
            report,
            verbose=getattr(args, "hardware_verbose", False),
        )

    return True


__all__ = [
    "register_health_command",
    "build_health_report",
    "handle_health_command",
    "health_record_to_dict",
    "print_health_report",
]
