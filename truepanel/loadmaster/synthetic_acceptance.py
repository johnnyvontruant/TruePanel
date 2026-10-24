"""Acceptance-only preflight for the disposable Crucial X10.

Never used by the production factory. Does not mount a disk, arm GPIO, or
perform a transfer. The operator's synthetic baseline receipt must be
independently established by a read-only USB comparison before this is used.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from time import monotonic
from typing import Any

from truepanel.cargo.copy_button import LoadmasterPhysicalPreflight

TEST_UUID = "6ADA-80D5"
TEST_SERIAL = "2532EA8D421A"
TEST_FILE = "PHYSICAL-COPY-ACCEPTANCE-20261023.bin"
TEST_SHA256 = "cd06734b5a2f259d3e43f603993607098edcabdc9e9d257fa4224e5d98b53214"


def accept_synthetic_preflight(
    receipt_path: Path, status: dict[str, Any]
) -> LoadmasterPhysicalPreflight | None:
    """Verify synthetic inventory/receipt and one precisely scoped new file."""
    try:
        if status.get("available") is not True or status.get("state") != "READY":
            return None
        if not 0 <= float(status.get("age", 999)) <= 5:
            return None
        receipt = json.loads(receipt_path.read_text())
        if (receipt.get("kind") != "truepanel.loadmaster_v2_synthetic_baseline"
            or receipt.get("authorized") is not False
            or receipt.get("schema_version") != 1):
            return None
        cartridge = receipt["cartridge"]
        drive = status["drive"]
        plan = status["plan"]
        if (cartridge.get("uuid") != TEST_UUID
            or cartridge.get("serial") != TEST_SERIAL
            or cartridge.get("label") != "Untitled"
            or any(drive.get(k) != value for k, value in (
                ("uuid", TEST_UUID), ("serial", TEST_SERIAL),
                ("name", "Untitled"),
                ("nas_path", cartridge["nas_path"]),
                ("usb_folder", cartridge["usb_folder"]),
            ))):
            return None
        nas = Path(cartridge["nas_path"])
        if not nas.is_dir() or nas.is_symlink() or not str(nas).startswith(
            "/mnt/SSDs/Applications/Loadmaster-V2-Lab/"
        ):
            return None
        entries = receipt["files"]
        if len(entries) != 3:
            return None
        for entry in entries:
            rel = Path(entry["relative_path"])
            if rel.is_absolute() or ".." in rel.parts:
                return None
            file = nas / rel
            if not file.is_file() or file.is_symlink():
                return None
            if file.stat().st_size != entry["size_bytes"]:
                return None
            if hashlib.sha256(file.read_bytes()).hexdigest() != entry["sha256"]:
                return None
        target = nas / TEST_FILE
        if (not target.is_file() or target.is_symlink()
            or target.stat().st_size != 65536
            or hashlib.sha256(target.read_bytes()).hexdigest() != TEST_SHA256):
            return None
        summary = plan["summary"]
        preview = plan["preview"]
        if (plan.get("state") != "READY" or plan.get("needs_confirmation") is not False
            or len(plan.get("digest", "")) != 64
            or int(summary.get("to_usb_files", 0)) != 1
            or int(summary.get("to_usb_bytes", 0)) != 65536
            or len(preview) != 1
            or preview[0].get("op") != "to_usb"
            or preview[0].get("path") != TEST_FILE
            or preview[0].get("size") != 65536
            or any(int(summary.get(k, 0)) != 0 for k in (
                "to_nas_files", "delete_usb_files", "retire_nas_files", "conflicts"
            ))):
            return None
        return LoadmasterPhysicalPreflight(
            cartridge_id="Untitled", cartridge_uuid=TEST_UUID,
            device_serial=TEST_SERIAL, plan_state="READY",
            backup_files=1, backup_bytes=65536,
            baseline_verified=True, identity_verified=True,
            backlog_verified=True, plan_digest=plan["digest"],
            generated_at_monotonic=monotonic(),
        )
    except (OSError, KeyError, ValueError, TypeError, AttributeError):
        return None


__all__ = ["accept_synthetic_preflight"]
