"""
CLI commands for the TruePanel host-agent boundary.

Host inspection commands are passive. They describe discovered capabilities,
standalone deployment readiness, or a future ownership cutover plan and never
grant hardware-control authority.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from truepanel.compatibility import collect_compatibility

from .capabilities import (
    HostAgentCapabilities,
    capabilities_from_compatibility,
)
from .cutover import (
    build_host_cutover_plan,
    format_host_cutover_plan,
)
from .readiness import (
    collect_host_readiness,
    format_host_readiness,
)


def add_host_subcommands(subcommands) -> None:
    """Register host-agent CLI commands."""

    host = subcommands.add_parser(
        "host",
        help="Inspect TruePanel host-agent state",
    )

    host_commands = host.add_subparsers(
        dest="host_command"
    )

    capabilities = host_commands.add_parser(
        "capabilities",
        help="Show passive host capability discovery",
    )

    capabilities.add_argument(
        "--json",
        action="store_true",
        dest="host_capabilities_json",
        help="Output machine-readable JSON",
    )

    capabilities.add_argument(
        "--root",
        dest="host_capabilities_root",
        help=(
            "Root filesystem to inspect; "
            "defaults to the running host"
        ),
    )

    readiness = host_commands.add_parser(
        "readiness",
        help=(
            "Report passive standalone Host Agent "
            "deployment readiness"
        ),
    )

    readiness.add_argument(
        "--json",
        action="store_true",
        dest="host_readiness_json",
        help="Output machine-readable JSON",
    )

    readiness.add_argument(
        "--root",
        dest="host_readiness_root",
        help=(
            "Filesystem root containing deployed service state; "
            "defaults to the running host"
        ),
    )

    cutover = host_commands.add_parser(
        "cutover-plan",
        help=(
            "Show the passive standalone Host Agent "
            "cutover and rollback plan"
        ),
    )

    cutover.add_argument(
        "--json",
        action="store_true",
        dest="host_cutover_json",
        help="Output machine-readable JSON",
    )

    cutover.add_argument(
        "--root",
        dest="host_cutover_root",
        help=(
            "Filesystem root containing deployed service state; "
            "defaults to the running host"
        ),
    )


def _status(capability: Any) -> str:
    if not capability.available:
        return "UNAVAILABLE"

    if capability.authorized:
        return "AUTHORIZED"

    return "AVAILABLE"


def print_host_capabilities(
    manifest: HostAgentCapabilities,
) -> None:
    """Print an operator-friendly host capability summary."""

    print()
    print("TruePanel Host Agent Capabilities")
    print("=================================")
    print()

    rows = (
        ("Platform", manifest.platform),
        ("LCD", manifest.lcd),
        ("Fan Telemetry", manifest.fan_telemetry),
        ("Fan Control", manifest.fan_control),
        ("Enclosure", manifest.enclosure),
    )

    for label, capability in rows:
        status = _status(capability)

        suffix = ""

        if (
            capability.available
            and not capability.authorized
            and label in {
                "LCD",
                "Fan Control",
                "Enclosure",
            }
        ):
            suffix = " [LOCKED]"

        print(
            f"{label:<15} "
            f"{status}{suffix}"
        )

    print()
    print(
        "Hardware authority: "
        + (
            "GRANTED"
            if manifest.hardware_authority_granted
            else "LOCKED"
        )
    )


def run_host_capabilities(
    *,
    json_output: bool = False,
    root: str | Path = "/",
) -> int:
    """
    Collect passive compatibility signals and expose the host manifest.

    The compatibility survey remains the canonical discovery layer.
    """

    report = collect_compatibility(
        root=root
    )

    manifest = capabilities_from_compatibility(
        report
    )

    if json_output:
        print(
            json.dumps(
                manifest.to_dict(),
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print_host_capabilities(
            manifest
        )

    return 0


def run_host_readiness(
    *,
    json_output: bool = False,
    root: str | Path = "/",
) -> int:
    """Report passive standalone Host Agent deployment readiness."""

    report = collect_host_readiness(
        root=root
    )

    if json_output:
        print(
            json.dumps(
                report.to_dict(),
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(
            format_host_readiness(
                report
            )
        )

    return 0 if report.prepared_safely else 1


def run_host_cutover_plan(
    *,
    json_output: bool = False,
    root: str | Path = "/",
) -> int:
    """Show the passive Host ownership cutover plan."""

    readiness = collect_host_readiness(
        root=root
    )
    plan = build_host_cutover_plan(
        readiness
    )

    if json_output:
        print(
            json.dumps(
                plan.to_dict(),
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(
            format_host_cutover_plan(
                plan
            )
        )

    return 0 if plan.prepared_safely else 1


def handle_host_command(args) -> int | None:
    """Dispatch host-agent CLI commands."""

    if getattr(args, "command", None) != "host":
        return None

    if (
        getattr(args, "host_command", None)
        == "capabilities"
    ):
        root = getattr(
            args,
            "host_capabilities_root",
            None,
        )

        return run_host_capabilities(
            json_output=bool(
                getattr(
                    args,
                    "host_capabilities_json",
                    False,
                )
            ),
            root=(
                Path(root).resolve()
                if root
                else Path("/")
            ),
        )

    if (
        getattr(args, "host_command", None)
        == "readiness"
    ):
        root = getattr(
            args,
            "host_readiness_root",
            None,
        )

        return run_host_readiness(
            json_output=bool(
                getattr(
                    args,
                    "host_readiness_json",
                    False,
                )
            ),
            root=(
                Path(root).resolve()
                if root
                else Path("/")
            ),
        )

    if (
        getattr(args, "host_command", None)
        == "cutover-plan"
    ):
        root = getattr(
            args,
            "host_cutover_root",
            None,
        )

        return run_host_cutover_plan(
            json_output=bool(
                getattr(
                    args,
                    "host_cutover_json",
                    False,
                )
            ),
            root=(
                Path(root).resolve()
                if root
                else Path("/")
            ),
        )

    return 0


__all__ = [
    "add_host_subcommands",
    "handle_host_command",
    "print_host_capabilities",
    "run_host_capabilities",
    "run_host_cutover_plan",
    "run_host_readiness",
]
