"""
Physical storage topology CLI command.
"""

from __future__ import annotations

import argparse
from typing import Any

from .manager import HardwareManager


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


def register_topology_command(
    actions: argparse._SubParsersAction,
) -> None:
    parser = actions.add_parser(
        "topology",
        help="Show physical bay topology",
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
        help="Show detailed kernel and enclosure fields",
    )


def print_topology_report(
    payload: dict[str, Any],
    *,
    verbose: bool,
) -> None:
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


def handle_topology_command(
    args: argparse.Namespace,
    *,
    manager: HardwareManager,
    print_json,
) -> bool:
    if getattr(args, "hardware_action", None) != "topology":
        return False

    payload = build_topology_report(manager)

    if getattr(args, "hardware_json", False):
        print_json(payload)
    else:
        print_topology_report(
            payload,
            verbose=getattr(args, "hardware_verbose", False),
        )

    return True


__all__ = [
    "build_topology_report",
    "handle_topology_command",
    "print_topology_report",
    "register_topology_command",
]
