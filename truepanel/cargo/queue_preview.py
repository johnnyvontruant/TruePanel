"""Read-only cartridge-aware pending-cargo overview.

This is a *presentation* of durable backlog state, not a physical backup
plan: no filesystem scan, source hash, USB mount, Copy-button confirmation,
cartridge permission mutation, or physical execution authority is produced.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .backlog import validate_backlog_payload
from .backup_executor import BackupExecutionError
from .cartridges import CartridgeDefinition, assign_cartridge
from .backup_transaction import _safe_parts
from .os_housekeeping import ignored_os_path

MAX_ROWS_PER_CARTRIDGE = 10
MAX_BACKLOG_ENTRIES = 250000


class QueuePreviewError(ValueError):
    pass


def _protected(relative: str) -> bool:
    # Permanent media exclusion; case-insensitive and deliberately broad.
    return any("daria" in part.casefold() for part in Path(relative).parts)


def preview_cartridge_queue(
    *, cartridges: list[CartridgeDefinition], backlog: dict[str, Any],
    cartridge_id: str | None = None, row_limit: int = 5,
) -> dict[str, Any]:
    """Summarize the ledger by registered cartridge, without accessing media.

    REVIEW is never READY: path/size are ledger observations, not verified
    files or operator approval. Missing/unmapped/unsupported entries remain
    visible as aggregate counts but never authorize transfer.
    """
    if (type(row_limit) is not int or
            not 1 <= row_limit <= MAX_ROWS_PER_CARTRIDGE):
        raise QueuePreviewError("invalid preview row limit")
    if not isinstance(cartridges, list) or not all(
            isinstance(c, CartridgeDefinition) for c in cartridges):
        raise QueuePreviewError("invalid cartridge registry")
    if cartridge_id is not None and not any(
            c.cartridge_id == cartridge_id for c in cartridges):
        raise QueuePreviewError("unknown cartridge ID")
    validated = validate_backlog_payload(backlog)
    items = validated["items"]
    if len(items) > MAX_BACKLOG_ENTRIES:
        raise QueuePreviewError("backlog exceeds bounded preview size")

    groups: dict[str, dict[str, Any]] = {}
    for c in cartridges:
        if cartridge_id is not None and c.cartridge_id != cartridge_id:
            continue
        groups[c.cartridge_id] = {
            "cartridge_id": c.cartridge_id, "label": c.label,
            "backup_policy_enabled": c.allow_backup,
            "ingest_policy_enabled": c.allow_ingest,
            "pending_items": 0, "pending_bytes": 0,
            "review_rows": 0, "unsupported_paths": 0,
            "excluded_protected": 0, "excluded_housekeeping": 0,
            "rows": [],
        }

    unmapped = 0
    for item in sorted(items, key=lambda x: (
            x["required_after"], x["current_path"])):
        source = Path(item["current_path"])
        owner = assign_cartridge(source, cartridges)
        if owner is None:
            unmapped += 1
            continue
        group = groups.get(owner.cartridge_id)
        if group is None:
            continue
        try:
            relative = source.relative_to(owner.source_prefix).as_posix()
        except ValueError:
            group["unsupported_paths"] += 1
            continue
        if _protected(relative):
            group["excluded_protected"] += 1
            continue
        if ignored_os_path(relative):
            group["excluded_housekeeping"] += 1
            continue
        try:
            _safe_parts(relative)
        except (ValueError, TypeError, BackupExecutionError):
            group["unsupported_paths"] += 1
            continue
        group["pending_items"] += 1
        group["pending_bytes"] += item["size_bytes"]
        if len(group["rows"]) < row_limit:
            group["rows"].append({
                "relative_path": relative,
                "size_bytes": item["size_bytes"],
                "required_after": item["required_after"],
                "state": "REVIEW",
                "reason": ("BACKUP_DISABLED" if not owner.allow_backup
                           else "NEEDS_SOURCE_AND_DEVICE_VERIFICATION"),
            })
            group["review_rows"] += 1

    return {
        "state": "LOADMASTER_READ_ONLY_QUEUE_PREVIEW",
        "source": "durable_backlog_only",
        "updated_at": validated["updated_at"],
        "cartridges": [groups[key] for key in sorted(groups)],
        "unmapped_entries": unmapped,
        "media_scanned": False, "source_hashes_verified": False,
        "usb_mount_checked": False, "transfer_enabled": False,
        "physical_authorized": False, "gpio_armed": False,
        "files_modified": False, "receipt_reconciliation": False,
        "note": "REVIEW rows are unverified ledger observations, not transfer plans",
    }
