#!/usr/bin/env python3
"""
TruePanel SGPIO and enclosure LED reconnaissance probe.

This tool is intentionally read-only. It searches standard Linux interfaces
for enclosure, LED, GPIO, SCSI, SAS, ATA, PCI, and platform-device evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


TEXT_ATTRIBUTES = (
    "brightness",
    "max_brightness",
    "trigger",
    "function",
    "color",
    "label",
    "type",
    "name",
    "state",
    "status",
    "fault",
    "locate",
    "active",
    "activity",
    "device",
    "modalias",
    "uevent",
)


def read_text(path: Path, limit: int = 8192) -> Optional[str]:
    try:
        if path.is_symlink():
            return str(path.resolve())

        if not path.is_file():
            return None

        value = path.read_text(
            encoding="utf-8",
            errors="replace",
        )[:limit].strip()

        return value or None
    except (OSError, PermissionError):
        return None


def describe_node(path: Path) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "name": path.name,
        "path": str(path),
    }

    if path.is_symlink():
        try:
            result["target"] = str(path.resolve())
        except OSError:
            pass

    attributes: Dict[str, str] = {}

    for attribute in TEXT_ATTRIBUTES:
        value = read_text(path / attribute)

        if value is not None:
            attributes[attribute] = value

    if attributes:
        result["attributes"] = attributes

    children = []

    try:
        for child in sorted(path.iterdir(), key=lambda item: item.name):
            if child.name.startswith("."):
                continue

            if child.is_symlink():
                try:
                    target = str(child.resolve())
                except OSError:
                    target = "<unresolved>"

                children.append(
                    {
                        "name": child.name,
                        "kind": "symlink",
                        "target": target,
                    }
                )
            elif child.is_dir():
                children.append(
                    {
                        "name": child.name,
                        "kind": "directory",
                    }
                )
            elif child.is_file():
                children.append(
                    {
                        "name": child.name,
                        "kind": "file",
                    }
                )
    except (OSError, PermissionError):
        pass

    if children:
        result["children"] = children

    return result


def scan_directory(path_string: str) -> Dict[str, Any]:
    path = Path(path_string)

    result: Dict[str, Any] = {
        "path": path_string,
        "exists": path.exists(),
        "entries": [],
    }

    if not path.exists():
        return result

    try:
        entries = sorted(path.iterdir(), key=lambda item: item.name)
    except (OSError, PermissionError) as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    result["entries"] = [describe_node(entry) for entry in entries]
    return result


def run_command(command: Iterable[str]) -> Dict[str, Any]:
    argv = list(command)

    try:
        completed = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

        return {
            "command": argv,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
    except FileNotFoundError:
        return {
            "command": argv,
            "available": False,
        }
    except subprocess.TimeoutExpired:
        return {
            "command": argv,
            "error": "command timed out",
        }


def scan_proc_file(path_string: str) -> Dict[str, Any]:
    path = Path(path_string)

    return {
        "path": path_string,
        "exists": path.exists(),
        "content": read_text(path, limit=65536),
    }


def build_report() -> Dict[str, Any]:
    sysfs_paths = (
        "/sys/class/leds",
        "/sys/class/enclosure",
        "/sys/class/gpio",
        "/sys/class/scsi_host",
        "/sys/class/scsi_device",
        "/sys/class/sas_host",
        "/sys/class/sas_phy",
        "/sys/class/sas_port",
        "/sys/class/ata_port",
        "/sys/class/block",
        "/sys/bus/platform/devices",
        "/sys/bus/pci/drivers",
    )

    commands = (
        ("uname", "-a"),
        ("lspci", "-nnk"),
        ("lsmod",),
        ("findmnt", "-no", "TARGET,SOURCE,FSTYPE,OPTIONS", "/sys"),
        ("udevadm", "info", "--export-db"),
        (
            "sh",
            "-c",
            "dmesg 2>/dev/null | "
            "grep -iE 'sgpio|enclosure|led|gpio|sas|sata|ahci|scsi|backplane' "
            "| tail -n 300",
        ),
    )

    report: Dict[str, Any] = {
        "probe": "TruePanel SGPIO/LED reconnaissance",
        "mode": "read-only",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hostname": platform.node(),
        "kernel": platform.release(),
        "platform": platform.platform(),
        "effective_uid": os.geteuid(),
        "sysfs": [scan_directory(path) for path in sysfs_paths],
        "proc": [
            scan_proc_file("/proc/modules"),
            scan_proc_file("/proc/cmdline"),
            scan_proc_file("/proc/scsi/scsi"),
        ],
        "commands": [run_command(command) for command in commands],
    }

    return report


def summarize(report: Dict[str, Any]) -> str:
    lines = [
        "TruePanel SGPIO/LED Reconnaissance",
        f'Host: {report["hostname"]}',
        f'Kernel: {report["kernel"]}',
        "Mode: READ-ONLY",
        "",
    ]

    for scan in report["sysfs"]:
        entries = scan.get("entries", [])

        lines.append(
            f'{scan["path"]}: '
            f'{"present" if scan["exists"] else "absent"} '
            f'({len(entries)} entries)'
        )

        for entry in entries:
            attributes = entry.get("attributes", {})
            details = []

            for name in (
                "brightness",
                "max_brightness",
                "trigger",
                "fault",
                "locate",
                "status",
                "state",
                "modalias",
            ):
                if name in attributes:
                    value = attributes[name].replace("\n", " ")
                    details.append(f"{name}={value[:100]}")

            suffix = f' [{", ".join(details)}]' if details else ""
            lines.append(f'  - {entry["name"]}{suffix}')

        lines.append("")

    command_by_name = {
        tuple(command.get("command", [])): command
        for command in report["commands"]
    }

    lspci = command_by_name.get(("lspci", "-nnk"), {})
    modules = command_by_name.get(("lsmod",), {})
    dmesg_command = next(
        (
            command
            for command in report["commands"]
            if command.get("command", [])[:2] == ["sh", "-c"]
        ),
        {},
    )

    lines.extend(
        [
            "Relevant PCI inventory:",
            lspci.get("stdout") or "<lspci unavailable or empty>",
            "",
            "Loaded modules:",
            modules.get("stdout") or "<lsmod unavailable or empty>",
            "",
            "Relevant kernel messages:",
            dmesg_command.get("stdout")
            or "<no matching messages or dmesg restricted>",
        ]
    )

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only SGPIO and enclosure LED reconnaissance"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit structured JSON instead of the human report",
    )
    args = parser.parse_args()

    report = build_report()

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(summarize(report))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
