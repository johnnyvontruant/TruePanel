"""
TruePanel hardware CLI command coordinator.

Individual hardware command modules own their parser registration, reporting,
rendering, and dispatch. This module provides the shared command tree and
top-level hardware summary.
"""

from __future__ import annotations

import argparse
import json
import platform
from typing import Any, Callable

from .health_commands import (
    build_health_report,
    handle_health_command,
    register_health_command,
)
from .manager import HardwareManager
from .storage_commands import (
    build_storage_report,
    handle_storage_command,
    register_storage_command,
)
from .topology_commands import (
    build_topology_report,
    handle_topology_command,
    register_topology_command,
)


CommandRegistrar = Callable[[argparse._SubParsersAction], None]
CommandHandler = Callable[..., bool]


COMMAND_REGISTRARS: tuple[CommandRegistrar, ...] = (
    register_storage_command,
    register_topology_command,
    register_health_command,
)

COMMAND_HANDLERS: tuple[CommandHandler, ...] = (
    handle_storage_command,
    handle_topology_command,
    handle_health_command,
)


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

    for register in COMMAND_REGISTRARS:
        register(actions)


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

    for handler in COMMAND_HANDLERS:
        if handler(
            args,
            manager=hardware,
            print_json=_print_json,
        ):
            return True

    payload = build_summary_report(hardware)

    if getattr(args, "hardware_json", False):
        _print_json(payload)
    else:
        _print_summary(payload)

    return True


__all__ = [
    "COMMAND_HANDLERS",
    "COMMAND_REGISTRARS",
    "add_hardware_subcommands",
    "build_health_report",
    "build_storage_report",
    "build_summary_report",
    "build_topology_report",
    "handle_hardware_command",
]
