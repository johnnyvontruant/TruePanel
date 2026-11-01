"""
Storage inventory CLI command.
"""

from __future__ import annotations

import argparse
from collections import Counter
from typing import Any

from .manager import HardwareManager


def _size_human(size_bytes: int) -> str:
    """Return a compact binary-size representation."""

    value = float(size_bytes)

    for suffix in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if value < 1024 or suffix == "PiB":
            if suffix == "B":
                return f"{int(value)} {suffix}"

            return f"{value:.1f} {suffix}"

        value /= 1024

    return f"{size_bytes} B"


def _drive_payload(drive) -> dict[str, Any]:
    return {
        "device": drive.device,
        "device_path": drive.device_path,
        "model": drive.model,
        "serial": drive.serial,
        "transport": drive.transport,
        "removable": drive.removable,
        "size_bytes": drive.size_bytes,
    }


def _storage_device_payload(entry) -> dict[str, Any]:
    payload = _drive_payload(entry.drive)

    payload.update(
        {
            "label": entry.label,
            "category": entry.category,
            "physical_bay": entry.physical_bay,
            "kernel_slot": entry.kernel_slot,
            "enclosure": entry.enclosure,
            "mapping_source": entry.mapping_source,
        }
    )

    return payload


def build_storage_report(
    hardware: HardwareManager,
) -> dict[str, Any]:
    devices = hardware.inventory.devices()
    categories = Counter(entry.category for entry in devices)

    return {
        "device_count": len(devices),
        "category_counts": {
            "front_bay": categories["front-bay"],
            "internal_nvme": categories["internal-nvme"],
            "boot_media": categories["boot-media"],
            "unassigned": categories["unassigned"],
        },
        "devices": [
            _storage_device_payload(entry)
            for entry in devices
        ],
    }


def register_storage_command(
    actions: argparse._SubParsersAction,
) -> None:
    parser = actions.add_parser(
        "storage",
        help="Show complete storage inventory",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        dest="hardware_json",
        help="Output machine-readable JSON",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        dest="hardware_verbose",
        help="Show model, size, transport, and enclosure details",
    )


def print_storage_report(
    payload: dict[str, Any],
    *,
    verbose: bool,
) -> None:
    print()
    print("TruePanel Storage Inventory")
    print("===========================")

    if not payload["devices"]:
        print("No storage devices discovered")
        return

    for entry in payload["devices"]:
        serial = entry["serial"] or "-"
        mapping = entry["mapping_source"]

        print(
            f"{entry['label']:<20} "
            f"{entry['device_path']:<14} "
            f"{serial:<18} "
            f"{entry['category']:<14} "
            f"{mapping}"
        )

        if verbose:
            print(f"  Model     : {entry['model'] or '-'}")
            print(f"  Transport : {entry['transport'] or 'unknown'}")
            print(f"  Size      : {_size_human(entry['size_bytes'])}")

            if entry["physical_bay"] is not None:
                print(f"  Bay       : {entry['physical_bay']}")

            if entry["kernel_slot"] is not None:
                print(f"  Slot      : {entry['kernel_slot']}")

            if entry["enclosure"]:
                print(f"  Enclosure : {entry['enclosure']}")

            print()


def handle_storage_command(
    args: argparse.Namespace,
    *,
    manager: HardwareManager,
    print_json,
) -> bool:
    if getattr(args, "hardware_action", None) != "storage":
        return False

    payload = build_storage_report(manager)

    if getattr(args, "hardware_json", False):
        print_json(payload)
    else:
        print_storage_report(
            payload,
            verbose=getattr(args, "hardware_verbose", False),
        )

    return True


__all__ = [
    "build_storage_report",
    "handle_storage_command",
    "print_storage_report",
    "register_storage_command",
]
