"""Read-only, fail-closed Mission Control view of Loadmaster evidence.

This module cannot arm GPIO, mount cartridges, run rsync or change a manifest.
A trusted host-side operator publishes a bounded snapshot on the SSD pool.
Mission Control reads that report; it never treats it as transfer authority.
"""
from __future__ import annotations

import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

KIND = "truepanel.loadmaster.flightdeck.v1"
MAX_BYTES = 128 * 1024
MAX_ACTIONS = 25
DIRECTIONS = {"NAS_TO_USB", "USB_TO_NAS"}
ACTION_STATES = {"READY", "VERIFIED", "CONFLICT", "REVIEW"}
MOUNT_STATES = {"ro", "unmounted", "unknown"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class FlightDeckError(ValueError):
    """Malformed, stale or unsafe source data."""


def _nonnegative(value: Any, name: str) -> int:
    if type(value) is not int or not 0 <= value <= 10**15:
        raise FlightDeckError(f"invalid {name}")
    return value


def _invalid(reason: str) -> dict[str, Any]:
    return {"enabled": True, "state": "INVALID", "read_only": True,
            "transfer_enabled": False, "physical_authorized": False,
            "invalid_reason": reason, "actions": []}


def read_flightdeck(path: Path | None, *, max_age_seconds: int = 86400,
                    now: datetime | None = None) -> dict[str, Any]:
    """Parse a restricted SSD report; never infer authorization from it."""
    if path is None:
        return {"enabled": False, "state": "DISABLED", "read_only": True,
                "transfer_enabled": False, "physical_authorized": False,
                "actions": []}
    try:
        if not path.is_absolute() or path.is_symlink():
            raise FlightDeckError("invalid snapshot path")
        # Reject links in the entire ancestor chain, not just the final file.
        if any(parent.is_symlink() for parent in path.parents):
            raise FlightDeckError("symlinked snapshot directory")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
                raise FlightDeckError("invalid snapshot file")
            if info.st_mode & 0o077:
                raise FlightDeckError("snapshot file must be private")
            content = os.read(fd, MAX_BYTES + 1)
            if len(content) > MAX_BYTES or len(content) != info.st_size:
                raise FlightDeckError("snapshot too large or changed")
        finally:
            os.close(fd)
        raw = json.loads(content)
        if not isinstance(raw, dict) or raw.get("kind") != KIND or raw.get("schema_version") != 1:
            raise FlightDeckError("unknown snapshot schema")
        if (raw.get("mode") != "PREVIEW_ONLY" or raw.get("read_only") is not True
                or raw.get("physical_authorized") is not False
                or raw.get("transfer_enabled") is not False):
            raise FlightDeckError("snapshot requests unsafe authority")
        stamp = raw.get("generated_at")
        if not isinstance(stamp, str):
            raise FlightDeckError("missing snapshot timestamp")
        generated = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if generated.tzinfo is None:
            raise FlightDeckError("timestamp must include timezone")
        age = ((now or datetime.now(timezone.utc)) -
               generated.astimezone(timezone.utc)).total_seconds()
        if age < -60 or age > max_age_seconds:
            raise FlightDeckError("stale or future-dated snapshot")
        cartridge = raw.get("cartridge")
        if not isinstance(cartridge, dict):
            raise FlightDeckError("missing cartridge")
        serial = cartridge.get("serial")
        uuid = cartridge.get("uuid")
        mode = cartridge.get("mount_mode")
        if (not isinstance(serial, str) or not re.fullmatch(r"[A-Za-z0-9]{6,64}", serial)
                or not isinstance(uuid, str) or not re.fullmatch(r"[A-Za-z0-9-]{4,80}", uuid)
                or mode not in MOUNT_STATES):
            raise FlightDeckError("invalid cartridge identity or mount state")
        actions = raw.get("actions")
        if not isinstance(actions, list) or len(actions) > MAX_ACTIONS:
            raise FlightDeckError("invalid action count")
        safe_actions = []
        for action in actions:
            if not isinstance(action, dict) or action.get("direction") not in DIRECTIONS:
                raise FlightDeckError("invalid action direction")
            path_text = action.get("relative_path")
            digest = action.get("sha256")
            if (not isinstance(path_text, str) or len(path_text) > 240
                    or not path_text or path_text.startswith("/")
                    or any(part in {"", ".", ".."} for part in path_text.split("/"))
                    or not isinstance(digest, str) or not HEX64.fullmatch(digest)
                    or action.get("status") not in ACTION_STATES):
                raise FlightDeckError("invalid action fingerprint or path")
            safe_actions.append({
                "direction": action["direction"], "relative_path": path_text,
                "size_bytes": _nonnegative(action.get("size_bytes"), "action size"),
                "sha256": digest, "status": action["status"]})
        summary = raw.get("summary")
        if not isinstance(summary, dict):
            raise FlightDeckError("missing summary")
        safe_summary = {key: _nonnegative(summary.get(key), key)
                        for key in ("export", "ingest", "verified", "conflicts")}
        if (safe_summary["export"] != sum(a["direction"] == "NAS_TO_USB" and a["status"] == "READY" for a in safe_actions)
                or safe_summary["ingest"] != sum(a["direction"] == "USB_TO_NAS" and a["status"] == "READY" for a in safe_actions)
                or safe_summary["verified"] != sum(a["status"] == "VERIFIED" for a in safe_actions)
                or safe_summary["conflicts"] != sum(a["status"] == "CONFLICT" for a in safe_actions)):
            raise FlightDeckError("summary does not match action evidence")
        receipts = raw.get("receipts")
        if not isinstance(receipts, dict):
            raise FlightDeckError("missing receipts")
        safe_receipts = {key: _nonnegative(receipts.get(key), key)
                         for key in ("backup", "ingest")}
        guard = receipts.get("guard")
        if guard not in ("RESTORED_RO", "UNKNOWN"):
            raise FlightDeckError("invalid guard state")
        safe_receipts["guard"] = guard
        return {
            "enabled": True, "state": "READY" if mode == "ro" else "REVIEW",
            "read_only": True, "transfer_enabled": False,
            "physical_authorized": False, "mode": "PREVIEW_ONLY",
            "generated_at": generated.isoformat(),
            "cartridge": {"serial": serial, "uuid": uuid, "mount_mode": mode,
                          "label": str(cartridge.get("label", "Cartridge"))[:80]},
            "summary": safe_summary, "actions": safe_actions,
            "receipts": safe_receipts,
        }
    except (OSError, UnicodeError, ValueError, TypeError, OverflowError):
        # No potentially sensitive source data is reflected to the web UI.
        return _invalid("Read-only flight-deck report missing, stale or invalid")
