"""Fail-closed production evidence qualification for Loadmaster physical Copy.

This module does not arm GPIO, mount media, or authorize a transfer by itself.
A separately verified per-cartridge baseline is required; a Cargo backup
manifest is not proof that an entire USB cartridge has been commissioned.
"""
from __future__ import annotations

import os
from pathlib import Path
from time import monotonic
from typing import Any, Callable

from truepanel.cargo.backlog import load_backlog
from truepanel.cargo.backup_manifest import validate_backup_manifest
from truepanel.cargo.cartridges import load_cartridge_registry
from truepanel.cargo.copy_button import LoadmasterPhysicalPreflight


def qualified_preflight(
    *,
    registry_path: Path,
    backlog_path: Path,
    manifest_path: Path,
    status: dict[str, Any],
    baseline_verified: Callable[[str, str], bool] | None = None,
) -> LoadmasterPhysicalPreflight | None:
    """Qualify one full, outbound-only plan or return no authority.

    baseline_verified is deliberately required. Never substitute valid JSON,
    file existence, or the mere presence of manifest entries for commissioning.
    """
    if baseline_verified is None:
        return None
    try:
        if status.get("available") is not True or status.get("state") != "READY":
            return None
        if not (0 <= float(status.get("age", 999)) <= 5):
            return None
        drive, plan = status.get("drive") or {}, status.get("plan") or {}
        summary = plan.get("summary") or {}
        if plan.get("state") != "READY" or plan.get("needs_confirmation") is not False:
            return None
        if not isinstance(plan.get("digest"), str) or len(plan["digest"]) != 64:
            return None
        if any(int(summary.get(k, 0)) != 0 for k in (
            "to_nas_files", "delete_usb_files", "retire_nas_files", "conflicts"
        )):
            return None
        files = int(summary.get("to_usb_files", 0))
        size = int(summary.get("to_usb_bytes", 0))
        if files < 1 or size < 1 or files > 40:
            # status.preview is capped at 40, so larger plans cannot be
            # independently reconciled from this public status.
            return None
        actions = plan.get("preview")
        if not isinstance(actions, list) or len(actions) != files:
            return None
        registry = load_cartridge_registry(registry_path)
        backlog = load_backlog(backlog_path)
        validate_backup_manifest(manifest_path)
        name, uuid, serial = (str(drive.get(k) or "") for k in ("name", "uuid", "serial"))
        if not (name and uuid and serial):
            return None
        matches = [c for c in registry if (
            c.label == name and c.uuid == uuid and c.device_serial == serial
            and c.allow_backup and c.delete_policy == "never"
            and str(c.source_prefix) == str(drive.get("nas_path"))
            and str(c.usb_relative_path) == str(drive.get("usb_folder"))
        )]
        if len(matches) != 1:
            return None
        cartridge = matches[0]
        if not baseline_verified(cartridge.cartridge_id, uuid):
            return None
        pending = {str(Path(i["current_path"])): int(i["size_bytes"])
                   for i in backlog["items"]}
        accounted = 0
        seen = set()
        for action in actions:
            if not isinstance(action, dict) or action.get("op") != "TO_USB":
                return None
            rel = action.get("path")
            if not isinstance(rel, str) or not rel or Path(rel).is_absolute() or ".." in Path(rel).parts:
                return None
            full = os.path.normpath(str(cartridge.source_prefix / rel))
            if full in seen or full not in pending:
                return None
            seen.add(full)
            accounted += pending[full]
        if accounted != size:
            return None
        return LoadmasterPhysicalPreflight(
            cartridge_id=name, cartridge_uuid=uuid, device_serial=serial,
            plan_state="READY", backup_files=files, backup_bytes=size,
            baseline_verified=True, identity_verified=True,
            backlog_verified=True, plan_digest=plan["digest"],
            generated_at_monotonic=monotonic(),
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


__all__ = ["qualified_preflight"]
