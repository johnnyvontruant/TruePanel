"""Read-only, verified-first reconciliation preview for the TV N-Z pilot.

This is NOT the durable backlog observer and CANNOT mutate or prune that
ledger. An SSD-hosted receipt is credited against one pending entry only if
its source AND USB copy were independently rehashed in the current session,
its SHA-256 and byte count match exactly, and its verified receipt timestamp
is no older than the ledger's required_after timestamp.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .backlog import validate_backlog_payload
from .backup_manifest import validate_backup_manifest


class ReceiptReconcileError(ValueError):
    pass


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise ReceiptReconcileError("missing evidence timestamp")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReceiptReconcileError("invalid evidence timestamp") from exc
    if stamp.tzinfo is None:
        raise ReceiptReconcileError("timezone-less evidence refused")
    return stamp.astimezone(timezone.utc)


def compare_verified_receipt(
    *, backlog: dict, manifest: dict,
    file_path: Path, relative_path: str,
    size_bytes: int, sha256: str,
    independently_verified_snapshot: dict,
) -> dict:
    """Return display-only, non-mutating receipt/ledger correlation.

    A report of VERIFIED_ELIGIBLE means only that *one existing backlog row*
    could be reconciled by a future, separately authorized durable observer.
    It is never permission to delete or transfer anything.
    """
    if (not isinstance(file_path, Path) or not file_path.is_absolute()
            or not isinstance(relative_path, str)
            or len(relative_path.split("/")) != 2
            or not isinstance(sha256, str) or len(sha256) != 64
            or any(c not in "0123456789abcdef" for c in sha256)
            or type(size_bytes) is not int or size_bytes < 1
            or any("daria" in part.casefold() for part in file_path.parts)):
        raise ReceiptReconcileError("invalid or protected pilot identity")
    ledger = validate_backlog_payload(backlog)
    if (not isinstance(manifest, dict)
            or manifest.get("kind") != "truepanel.cargo_backup_manifest"
            or not isinstance(manifest.get("items"), list)):
        raise ReceiptReconcileError("invalid pilot receipt manifest")
    snapshot = independently_verified_snapshot
    if (not isinstance(snapshot, dict)
            or snapshot.get("mode") != "PREVIEW_ONLY"
            or snapshot.get("physical_authorized") is not False
            or snapshot.get("transfer_enabled") is not False
            or snapshot.get("read_only") is not True
            or snapshot.get("summary", {}).get("verified") != 1
            or snapshot.get("receipts", {}).get("backup") != 1
            or snapshot.get("cartridge", {}).get("mount_mode") != "ro"
            or snapshot.get("actions") != [{
                "direction": "NAS_TO_USB", "relative_path": relative_path,
                "size_bytes": size_bytes, "sha256": sha256,
                "status": "VERIFIED",
            }]):
        raise ReceiptReconcileError("independent live file verification required")
    matches = [r for r in manifest["items"] if
               isinstance(r, dict) and r.get("path") == str(file_path)]
    if len(matches) != 1:
        raise ReceiptReconcileError("nonunique or absent pilot receipt")
    receipt = matches[0]
    if (receipt.get("size_bytes") != size_bytes
            or receipt.get("sha256") != sha256):
        raise ReceiptReconcileError("receipt fingerprint mismatched")
    backed_up_at = _timestamp(receipt.get("backed_up_at"))
    queued = [i for i in ledger["items"]
              if i["current_path"] == str(file_path)]
    if len(queued) > 1:
        raise ReceiptReconcileError("duplicate pilot backlog row")
    state = "NOT_CURRENTLY_QUEUED"
    eligible = 0
    queued_size = None
    required_after = None
    if queued:
        row = queued[0]
        queued_size = row["size_bytes"]
        required_at = _timestamp(row["required_after"])
        required_after = required_at.isoformat()
        if queued_size != size_bytes:
            state = "SIZE_MISMATCH_HOLD"
        elif backed_up_at < required_at:
            state = "STALE_RECEIPT_HOLD"
        else:
            state = "VERIFIED_ELIGIBLE"
            eligible = 1
    return {
        "state": "LOADMASTER_READ_ONLY_RECONCILIATION",
        "pilot_status": state,
        "source": str(file_path),
        "source_relative_path": relative_path,
        "bytes": size_bytes, "sha256": sha256,
        "backup_receipt_at": backed_up_at.isoformat(),
        "required_after": required_after,
        "queued_size_bytes": queued_size,
        "pending_before": len(ledger["items"]),
        "eligible_for_future_reconciliation": eligible,
        "pending_after_hypothetical": len(ledger["items"]) - eligible,
        "ledger_mutated": False,
        "manifest_mutated": False,
        "usb_written": False,
        "hdd_written": False,
        "physical_authorized": False,
        "backlog_entry_removed": False,
        "note": "Hypothetical counts only. No durable backlog or Mission Control configuration changed.",
    }
