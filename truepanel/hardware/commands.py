"""
TruePanel hardware CLI commands.

Exposes the read-only Hardware Abstraction Layer through human-readable and
machine-readable reports.
"""

from __future__ import annotations

import argparse
import json
import platform
from collections import Counter
from typing import Any, Sequence

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


def _front_bay_payload(bay) -> dict[str, Any]:
    return {
        "physical_bay": bay.physical_bay,
        "kernel_slot": bay.kernel_slot,
        "installed": bay.installed,
        "status": bay.status,
        "device": bay.device,
        "device_path": bay.device_path,
        "model": bay.model,
        "serial": bay.serial,
        "wwid": bay.wwid,
        "enclosure": bay.enclosure,
        "mapping_source": bay.mapping_source,
    }


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


def build_topology_report(
    hardware: HardwareManager,
) -> dict[str, Any]:
    bays = hardware.inventory.front_bays()

    return {
        "bay_count": len(bays),
        "installed_count": sum(bay.installed for bay in bays),
        "configured_count": sum(
            bay.mapping_source == "configured"
            for bay in bays
        ),
        "bays": [
            _front_bay_payload(bay)
            for bay in bays
        ],
    }


def build_summary_report(
    hardware: HardwareManager,
) -> dict[str, Any]:
    storage = build_storage_report(hardware)
    topology = build_topology_report(hardware)

    return {
        "hostname": platform.node() or "unknown",
        "storage": {
            "device_count": storage["device_count"],
            "category_counts": storage["category_counts"],
        },
        "topology": {
            "bay_count": topology["bay_count"],
            "installed_count": topology["installed_count"],
            "configured_count": topology["configured_count"],
        },
        "controllers": {
            "registered": list(hardware.registered()),
            "loaded": list(hardware.loaded()),
        },
    }


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _print_summary(payload: dict[str, Any]) -> None:
    storage = payload["storage"]
    topology = payload["topology"]
    categories = storage["category_counts"]

    print()
    print("TruePanel Hardware")
    print("==================")
    print(f"Host: {payload['hostname']}")

    print()
    print("Storage")
    print("-------")
    print(f"Devices       : {storage['device_count']}")
    print(f"Front Bays    : {categories['front_bay']}")
    print(f"Internal NVMe : {categories['internal_nvme']}")
    print(f"Boot Media    : {categories['boot_media']}")
    print(f"Unassigned    : {categories['unassigned']}")

    print()
    print("Topology")
    print("--------")
    print(f"Physical Bays : {topology['bay_count']}")
    print(f"Installed     : {topology['installed_count']}")
    print(f"Configured    : {topology['configured_count']}")

    print()
    print("Hardware Services")
    print("-----------------")
    print(
        "Registered: "
        + ", ".join(payload["controllers"]["registered"])
    )
    print(
        "Loaded    : "
        + (
            ", ".join(payload["controllers"]["loaded"])
            or "none"
        )
    )


def _print_storage(payload: dict[str, Any], *, verbose: bool) -> None:
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


def _print_topology(payload: dict[str, Any], *, verbose: bool) -> None:
    print()
    print("TruePanel Storage Topology")
    print("==========================")

    if not payload["bays"]:
        print("No enclosure bays discovered")
        return

    for bay in payload["bays"]:
        device = bay["device_path"] or "-"
        serial = bay["serial"] or "-"
        mapping = bay["mapping_source"]

        print(
            f"Bay {bay['physical_bay']:<3} "
            f"Slot {bay['kernel_slot']:<3} "
            f"{device:<14} "
            f"{serial:<18} "
            f"{mapping}"
        )

        if verbose:
            print(f"  Installed : {'yes' if bay['installed'] else 'no'}")
            print(f"  Status    : {bay['status'] or 'unknown'}")
            print(f"  Model     : {bay['model'] or '-'}")
            print(f"  WWID      : {bay['wwid'] or '-'}")
            print(f"  Enclosure : {bay['enclosure'] or '-'}")
            print()


def add_hardware_subcommands(
    subcommands: argparse._SubParsersAction,
) -> None:
    """Register the production hardware command tree."""

    hardware = subcommands.add_parser(
        "hardware",
        help="Inspect TruePanel hardware",
    )

    hardware.add_argument(
        "--json",
        action="store_true",
        dest="hardware_json",
        help="Output machine-readable JSON",
    )
    hardware.add_argument(
        "--verbose",
        action="store_true",
        dest="hardware_verbose",
        help="Show detailed hardware fields",
    )

    actions = hardware.add_subparsers(dest="hardware_action")

    storage = actions.add_parser(
        "storage",
        help="Show complete storage inventory",
    )
    storage.add_argument(
        "--json",
        action="store_true",
        dest="hardware_json",
        help="Output machine-readable JSON",
    )
    storage.add_argument(
        "--verbose",
        action="store_true",
        dest="hardware_verbose",
        help="Show model, size, transport, and enclosure details",
    )

    topology = actions.add_parser(
        "topology",
        help="Show physical bay topology",
    )
    topology.add_argument(
        "--json",
        action="store_true",
        dest="hardware_json",
        help="Output machine-readable JSON",
    )
    topology.add_argument(
        "--verbose",
        action="store_true",
        dest="hardware_verbose",
        help="Show detailed kernel and enclosure fields",
    )


def handle_hardware_command(
    args: argparse.Namespace,
    *,
    manager: HardwareManager | None = None,
) -> bool:
    """
    Handle a hardware CLI request.

    Returns True when the parsed command belonged to the hardware command tree.
    """

    if getattr(args, "command", None) != "hardware":
        return False

    hardware = manager or HardwareManager()
    action = getattr(args, "hardware_action", None)
    json_output = getattr(args, "hardware_json", False)
    verbose = getattr(args, "hardware_verbose", False)

    if action == "storage":
        payload = build_storage_report(hardware)

        if json_output:
            _print_json(payload)
        else:
            _print_storage(payload, verbose=verbose)

        return True

    if action == "topology":
        payload = build_topology_report(hardware)

        if json_output:
            _print_json(payload)
        else:
            _print_topology(payload, verbose=verbose)

        return True

    payload = build_summary_report(hardware)

    if json_output:
        _print_json(payload)
    else:
        _print_summary(payload)

    return True


__all__ = [
    "add_hardware_subcommands",
    "build_storage_report",
    "build_summary_report",
    "build_topology_report",
    "handle_hardware_command",
]
