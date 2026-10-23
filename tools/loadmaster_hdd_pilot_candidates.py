#!/usr/bin/env python3
"""READ-ONLY Loadmaster HDD pilot candidate survey, not an executor.

Inspects the existing durable pending-cargo ledger and registered HDD scopes.
No USB required. Does not hash media, mount, arm GPIO, copy, or modify files.
A DEGRADED pool is displayed as an explicit risk acknowledgement, not a
silent or implicit approval for storage mutation.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
from pathlib import Path

from truepanel.cargo.backlog import load_backlog
from truepanel.cargo.cartridges import assign_cartridge, load_cartridge_registry
from truepanel.cargo.os_housekeeping import ignored_os_path

REGISTRY = Path("/var/lib/truepanel/loadmaster/cartridges.json")
BACKLOG = Path("/var/lib/truepanel/loadmaster/pending-cargo.json")
HDD_ROOT = Path("/mnt/HDDs")
MAX_CANDIDATES = 3
MAX_BYTES = 4 * 1024 ** 3


def _safe_regular_file(path: Path, *, root: Path, expected_size: int) -> bool:
    if (not path.is_absolute() or not path.is_relative_to(root)
            or type(expected_size) is not int or expected_size <= 0):
        return False
    # Check all components, including parent directories, without following links.
    for item in (path, *path.parents):
        if item.is_symlink():
            return False
        if item == root:
            break
    try:
        st = path.lstat()
    except OSError:
        return False
    return stat.S_ISREG(st.st_mode) and st.st_size == expected_size


def _protected(relative: Path) -> bool:
    # Daria is an immutable fan restoration. Never include it in automated
    # planning or a pilot even if a cartridge or ledger includes it.
    return any("daria" in component.casefold() for component in relative.parts)


def select_hdd_candidates(*, registry: Path, backlog: Path,
                          library_root: Path = HDD_ROOT,
                          pool_health: str = "UNKNOWN",
                          max_bytes: int = MAX_BYTES) -> dict:
    if (not library_root.is_absolute() or library_root.is_symlink()
            or not library_root.is_dir() or max_bytes < 1):
        raise ValueError("unsafe HDD library root")
    cartridges = load_cartridge_registry(registry)
    ledger = load_backlog(backlog)
    counts = {
        "ledger_items": len(ledger["items"]),
        "out_of_scope": 0,
        "unregistered": 0,
        "skipped_housekeeping": 0,
        "skipped_protected_media": 0,
        "unsupported_depth": 0,
        "missing_or_changed": 0,
        "oversized": 0,
    }
    eligible = []
    for item in ledger["items"]:
        source = Path(item["current_path"])
        if not source.is_relative_to(library_root):
            counts["out_of_scope"] += 1
            continue
        cartridge = assign_cartridge(source, cartridges)
        if (cartridge is None or not cartridge.allow_backup
                or not cartridge.source_prefix.is_relative_to(library_root)):
            counts["unregistered"] += 1
            continue
        relative = source.relative_to(cartridge.source_prefix)
        if _protected(relative) or _protected(source.relative_to(library_root)):
            counts["skipped_protected_media"] += 1
            continue
        if ignored_os_path(relative.as_posix()):
            counts["skipped_housekeeping"] += 1
            continue
        if len(relative.parts) != 2:
            counts["unsupported_depth"] += 1
            continue
        size = item["size_bytes"]
        if size > max_bytes:
            counts["oversized"] += 1
            continue
        if not _safe_regular_file(source, root=library_root, expected_size=size):
            counts["missing_or_changed"] += 1
            continue
        eligible.append({
            "cartridge_id": cartridge.cartridge_id,
            "cartridge_label": cartridge.label,
            "cartridge_uuid": cartridge.uuid,
            "trusted_device_serial_registered": bool(cartridge.device_serial),
            "source": str(source),
            "relative_path": relative.as_posix(),
            "size_bytes": size,
            "direction": "NAS_TO_USB",
        })
    eligible.sort(key=lambda row: (row["size_bytes"], row["cartridge_id"], row["source"]))
    return {
        "state": "HDD_PILOT_READ_ONLY_CANDIDATES" if eligible else "HDD_PILOT_NO_CANDIDATES",
        "schema_version": 1,
        "pool_health": str(pool_health),
        "degraded_pool_risk": str(pool_health).upper() != "ONLINE",
        "risk_policy": "DEGRADED_ALLOWED_FOR_SURVEY_ONLY",
        "executed": False, "usb_written": False, "hdd_written": False,
        "physical_authorized": False,
        "scope": "registered_HDD_library_NAS_TO_USB_only",
        "candidate_limit": MAX_CANDIDATES,
        "max_candidate_bytes": max_bytes,
        "counts": counts,
        "eligible_total": len(eligible),
        "candidates": eligible[:MAX_CANDIDATES],
        "remaining_gates": [
            "PLUG_REGISTERED_BACKUP_CARTRIDGE_AND_ATTEST_BY_ID_UUID_SERIAL_READ_ONLY",
            "QUALIFY_HOST_ACTUATOR_FOR_EXPLICIT_HDD_SOURCE_SCOPE",
            "VERIFY_NO_OVERWRITE_DESTINATION_AND_CAPACITY",
            "PRESERVE_PHYSICAL_COPY_BUTTON_APPROVAL_AND_INDEPENDENT_RO_WATCHDOG",
            "EXECUTE_SEPARATE_OPERATOR_AUTHORIZED_PILOT_ONLY",
        ],
    }


def _pool_health() -> str:
    try:
        result = subprocess.run(
            ["zpool", "list", "-H", "-o", "health", "HDDs"],
            check=False, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return "UNKNOWN"
    value = result.stdout.strip()
    return value if result.returncode == 0 and re.fullmatch(r"[A-Z]+", value) else "UNKNOWN"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    parser.add_argument("--backlog", type=Path, default=BACKLOG)
    args = parser.parse_args()
    try:
        report = select_hdd_candidates(
            registry=args.registry, backlog=args.backlog,
            pool_health=_pool_health())
    except (OSError, ValueError, RuntimeError) as err:
        print(json.dumps({"state": "HDD_PILOT_PREFLIGHT_HOLD",
                          "reason": str(err), "executed": False}, indent=2))
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
