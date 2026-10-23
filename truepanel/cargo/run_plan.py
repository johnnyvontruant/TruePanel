"""Combined, digest-sealed Loadmaster run plans for one docked cartridge.

A run plan answers: *if the operator presses Copy right now, exactly which
files move, in which direction, and why?* It combines two independent scopes:

* **Backup (NAS -> USB)** comes only from the durable backlog that the
  Sonarr/Radarr observer maintains, via :func:`build_backlog_backup_plan`.
  Unrelated NAS files are never swept onto a cartridge.
* **Ingest (USB -> NAS)** compares the cartridge tree with the NAS tree and the
  commissioned inventory baseline. Only files that are new on the cartridge
  (absent from NAS *and* from the baseline), or that changed on the cartridge
  while the NAS copy stayed at baseline, become ingest work.

Anything ambiguous becomes a conflict, and any conflict turns the whole plan
into ``HOLD`` so the Copy button stays disarmed. Informational notices (for
example a cartridge file whose NAS original was retired by an upgrade) are
reported but never block and never cause deletion.

The plan digest covers every action plus each source file's size and mtime.
The executor re-plans immediately before copying and refuses to run unless the
fresh digest equals the digest the physical Copy press confirmed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .cartridges import CartridgeDefinition, assign_cartridge
from .copy_button import LoadmasterPhysicalPreflight
from .loadmaster import (
    DEFAULT_IGNORED_NAMES,
    DEFAULT_MTIME_TOLERANCE_SECONDS,
    FileFingerprint,
    LoadmasterPlanError,
    _fingerprints_match,
    _regular_file_fingerprint,
    build_backlog_backup_plan,
    scan_tree,
)

LOADMASTER_RUN_PLAN_SCHEMA_VERSION = 1
LOADMASTER_RUN_PLAN_KIND = "truepanel.loadmaster_run_plan"

# Operating-system clutter that commonly appears on removable drives. It is
# never media and is never ingested.
USB_IGNORED_NAMES = DEFAULT_IGNORED_NAMES | frozenset(
    {
        "$RECYCLE.BIN",
        "Thumbs.db",
        "desktop.ini",
        "lost+found",
        ".TemporaryItems",
        ".DocumentRevisions-V100",
    }
)
USB_IGNORED_PREFIXES = ("._", ".Trash-")

UPDATE_REASONS = frozenset({"BACKLOG_UPDATED", "USB_UPDATED", "NAS_UPDATED"})


@dataclass(frozen=True)
class RunAction:
    direction: str
    relative_path: str
    size_bytes: int
    reason: str
    source_mtime_ns: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction,
            "relative_path": self.relative_path,
            "size_bytes": self.size_bytes,
            "reason": self.reason,
            "source_mtime_ns": self.source_mtime_ns,
        }


def _usb_clutter(relative: str) -> bool:
    return any(
        part.startswith(USB_IGNORED_PREFIXES) for part in PurePosixPath(relative).parts
    )


def scan_cartridge_tree(root: Path) -> dict[str, FileFingerprint]:
    """Scan a cartridge tree, ignoring removable-drive clutter."""

    files = scan_tree(root, ignored_names=USB_IGNORED_NAMES)
    return {
        relative: fingerprint
        for relative, fingerprint in files.items()
        if not _usb_clutter(relative)
    }


def _fp_dict(value: FileFingerprint | None) -> dict[str, int] | None:
    if value is None:
        return None
    return {"size_bytes": value.size_bytes, "mtime_ns": value.mtime_ns}


def build_ingest_actions(
    *,
    nas: dict[str, FileFingerprint],
    usb: dict[str, FileFingerprint],
    baseline: dict[str, FileFingerprint],
    tolerance_seconds: float = DEFAULT_MTIME_TOLERANCE_SECONDS,
) -> tuple[list[RunAction], list[dict[str, Any]], list[dict[str, Any]], int]:
    """Return (actions, conflicts, notices, unchanged) for USB -> NAS."""

    actions: list[RunAction] = []
    conflicts: list[dict[str, Any]] = []
    notices: list[dict[str, Any]] = []
    unchanged = 0

    def match(left: FileFingerprint, right: FileFingerprint) -> bool:
        return _fingerprints_match(left, right, tolerance_seconds=tolerance_seconds)

    for relative in sorted(usb):
        usb_fp = usb[relative]
        nas_fp = nas.get(relative)
        old_fp = baseline.get(relative)

        if nas_fp is None:
            if old_fp is not None:
                # The NAS copy was deleted, renamed, or upgraded since the last
                # verified sync. Delete policy is "never", so the cartridge copy
                # simply stays behind; it is not re-imported.
                notices.append({"relative_path": relative, "reason": "RETIRED_ON_NAS"})
                continue

            actions.append(
                RunAction(
                    direction="USB_TO_NAS",
                    relative_path=relative,
                    size_bytes=usb_fp.size_bytes,
                    reason="NEW_ON_USB",
                    source_mtime_ns=usb_fp.mtime_ns,
                )
            )
            continue

        if match(nas_fp, usb_fp):
            unchanged += 1
            continue

        if old_fp is None:
            conflicts.append(
                {
                    "relative_path": relative,
                    "reason": "DIVERGENT_WITHOUT_BASELINE",
                    "nas": _fp_dict(nas_fp),
                    "usb": _fp_dict(usb_fp),
                    "baseline": None,
                }
            )
            continue

        nas_same = match(nas_fp, old_fp)
        usb_same = match(usb_fp, old_fp)

        if nas_same and not usb_same:
            actions.append(
                RunAction(
                    direction="USB_TO_NAS",
                    relative_path=relative,
                    size_bytes=usb_fp.size_bytes,
                    reason="USB_UPDATED",
                    source_mtime_ns=usb_fp.mtime_ns,
                )
            )
            continue

        if usb_same and not nas_same:
            # NAS is newer. Backup is backlog-scoped; if this change is in the
            # backlog the backup half of the plan carries it.
            notices.append({"relative_path": relative, "reason": "NAS_NEWER"})
            continue

        conflicts.append(
            {
                "relative_path": relative,
                "reason": "BOTH_SIDES_CHANGED",
                "nas": _fp_dict(nas_fp),
                "usb": _fp_dict(usb_fp),
                "baseline": _fp_dict(old_fp),
            }
        )

    return actions, conflicts, notices, unchanged


def backlog_items_for_cartridge(
    backlog: dict[str, Any],
    *,
    cartridge: CartridgeDefinition,
    cartridges: list[CartridgeDefinition],
) -> list[dict[str, Any]]:
    """Return durable backlog rows owned by exactly this cartridge."""

    items = backlog.get("items")
    if not isinstance(items, list):
        raise LoadmasterPlanError("Loadmaster backlog items are unavailable")

    owned = []
    for item in items:
        if not isinstance(item, dict):
            raise LoadmasterPlanError("Loadmaster backlog item must be an object")
        owner = assign_cartridge(str(item.get("current_path") or ""), cartridges)
        if owner is not None and owner.cartridge_id == cartridge.cartridge_id:
            owned.append(item)
    return owned


def _split_live_backlog(
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Separate backlog rows whose source still matches from stale rows.

    A backlog row whose NAS file vanished (upgrade/rename) or changed size since
    observation cannot be proven, so it is reported and skipped rather than
    blocking every other file on the cartridge. The observer refreshes rows on
    the next Servarr import of that path.
    """

    live = []
    notices = []

    for item in items:
        source = Path(str(item.get("current_path") or ""))
        try:
            fingerprint = _regular_file_fingerprint(source)
        except LoadmasterPlanError as error:
            notices.append(
                {
                    "relative_path": str(source),
                    "reason": "BACKLOG_SOURCE_UNREADABLE",
                    "detail": str(error),
                }
            )
            continue

        if fingerprint is None:
            notices.append(
                {"relative_path": str(source), "reason": "BACKLOG_SOURCE_GONE"}
            )
            continue

        if fingerprint.size_bytes != item.get("size_bytes"):
            notices.append(
                {"relative_path": str(source), "reason": "BACKLOG_SOURCE_CHANGED"}
            )
            continue

        live.append(item)

    return live, notices


def plan_digest(
    *,
    cartridge: CartridgeDefinition,
    actions: list[RunAction],
) -> str:
    material = json.dumps(
        {
            "kind": LOADMASTER_RUN_PLAN_KIND,
            "cartridge_id": cartridge.cartridge_id,
            "cartridge_uuid": cartridge.uuid.casefold(),
            "actions": [action.as_dict() for action in actions],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def build_run_plan(
    *,
    cartridge: CartridgeDefinition,
    cartridges: list[CartridgeDefinition],
    usb_mount: Path,
    backlog: dict[str, Any],
    inventory: dict[str, FileFingerprint],
    ingest_enabled: bool,
    tolerance_seconds: float = DEFAULT_MTIME_TOLERANCE_SECONDS,
) -> dict[str, Any]:
    """Build the combined backup + ingest plan for one mounted cartridge."""

    nas_root = cartridge.source_prefix
    usb_root = usb_mount / cartridge.usb_relative_path

    notices: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    actions: list[RunAction] = []
    backup_unchanged = 0
    ingest_unchanged = 0

    # ---- backup half: durable backlog only
    backup_scope = backlog_items_for_cartridge(
        backlog, cartridge=cartridge, cartridges=cartridges
    )
    live_items, stale_notices = _split_live_backlog(backup_scope)
    notices.extend(stale_notices)

    if cartridge.allow_backup:
        backup_plan = build_backlog_backup_plan(
            cartridge=cartridge,
            usb_mount=usb_mount,
            backlog_items=live_items,
            inventory=inventory,
            tolerance_seconds=tolerance_seconds,
        )
        conflicts.extend(backup_plan["conflicts"])
        backup_unchanged = int(backup_plan["summary"]["unchanged_files"])

        for raw in backup_plan["actions"]:
            source = nas_root / raw["relative_path"]
            fingerprint = _regular_file_fingerprint(source)
            if fingerprint is None:
                raise LoadmasterPlanError(f"Loadmaster source vanished: {source}")
            actions.append(
                RunAction(
                    direction="NAS_TO_USB",
                    relative_path=raw["relative_path"],
                    size_bytes=fingerprint.size_bytes,
                    reason=raw["reason"],
                    source_mtime_ns=fingerprint.mtime_ns,
                )
            )
    elif live_items:
        conflicts.extend(
            {
                "relative_path": str(item.get("current_path")),
                "reason": "BACKUP_DISABLED",
                "nas": None,
                "usb": None,
                "baseline": None,
            }
            for item in live_items
        )

    # ---- ingest half: new or updated files on the cartridge
    if ingest_enabled and cartridge.allow_ingest:
        if not usb_root.is_dir():
            raise LoadmasterPlanError(f"USB cartridge root is unavailable: {usb_root}")
        usb_files = scan_cartridge_tree(usb_root)
        nas_files = scan_tree(nas_root)
        ingest, ingest_conflicts, ingest_notices, ingest_unchanged = (
            build_ingest_actions(
                nas=nas_files,
                usb=usb_files,
                baseline=inventory,
                tolerance_seconds=tolerance_seconds,
            )
        )
        actions.extend(ingest)
        conflicts.extend(ingest_conflicts)
        notices.extend(ingest_notices)

    # ---- one path may never move in both directions in one run
    seen: dict[str, str] = {}
    for action in actions:
        previous = seen.get(action.relative_path)
        if previous is not None and previous != action.direction:
            conflicts.append(
                {
                    "relative_path": action.relative_path,
                    "reason": "BIDIRECTIONAL_ACTION",
                    "nas": None,
                    "usb": None,
                    "baseline": None,
                }
            )
        seen[action.relative_path] = action.direction

    actions.sort(key=lambda item: (item.direction, item.relative_path))

    backup_actions = [item for item in actions if item.direction == "NAS_TO_USB"]
    ingest_actions = [item for item in actions if item.direction == "USB_TO_NAS"]

    state = "HOLD" if conflicts else "READY" if actions else "CLEAR"

    return {
        "schema_version": LOADMASTER_RUN_PLAN_SCHEMA_VERSION,
        "kind": LOADMASTER_RUN_PLAN_KIND,
        "delete_policy": "never",
        "state": state,
        "cartridge": cartridge.public_dict(),
        "nas_root": str(nas_root),
        "usb_root": str(usb_root),
        "ingest_enabled": bool(ingest_enabled and cartridge.allow_ingest),
        "summary": {
            "backlog_items": len(backup_scope),
            "backup_files": len(backup_actions),
            "backup_bytes": sum(item.size_bytes for item in backup_actions),
            "ingest_files": len(ingest_actions),
            "ingest_bytes": sum(item.size_bytes for item in ingest_actions),
            "backup_unchanged_files": backup_unchanged,
            "ingest_unchanged_files": ingest_unchanged,
            "conflicts": len(conflicts),
            "notices": len(notices),
        },
        "actions": [item.as_dict() for item in actions],
        "conflicts": conflicts,
        "notices": notices,
        "digest": plan_digest(cartridge=cartridge, actions=actions),
    }


def physical_preflight(
    *,
    plan: dict[str, Any],
    cartridge: CartridgeDefinition,
    device_serial: str,
    identity_verified: bool,
    baseline_verified: bool,
    backlog_verified: bool,
    generated_at_monotonic: float,
) -> LoadmasterPhysicalPreflight:
    """Translate a run plan into the Copy-button gate's preflight evidence."""

    summary = plan.get("summary") or {}
    return LoadmasterPhysicalPreflight(
        cartridge_id=cartridge.cartridge_id,
        cartridge_uuid=cartridge.uuid,
        device_serial=device_serial,
        plan_state=str(plan.get("state") or ""),
        backup_files=int(summary.get("backup_files") or 0),
        backup_bytes=int(summary.get("backup_bytes") or 0),
        ingest_files=int(summary.get("ingest_files") or 0),
        ingest_bytes=int(summary.get("ingest_bytes") or 0),
        baseline_verified=bool(baseline_verified),
        identity_verified=bool(identity_verified),
        backlog_verified=bool(backlog_verified),
        plan_digest=str(plan.get("digest") or ""),
        generated_at_monotonic=float(generated_at_monotonic),
    )


def actions_from_plan(plan: dict[str, Any]) -> list[RunAction]:
    result = []
    for raw in plan.get("actions") or []:
        result.append(
            RunAction(
                direction=str(raw["direction"]),
                relative_path=str(raw["relative_path"]),
                size_bytes=int(raw["size_bytes"]),
                reason=str(raw["reason"]),
                source_mtime_ns=int(raw["source_mtime_ns"]),
            )
        )
    return result


__all__ = [
    "LOADMASTER_RUN_PLAN_KIND",
    "LOADMASTER_RUN_PLAN_SCHEMA_VERSION",
    "RunAction",
    "UPDATE_REASONS",
    "USB_IGNORED_NAMES",
    "actions_from_plan",
    "backlog_items_for_cartridge",
    "build_ingest_actions",
    "build_run_plan",
    "physical_preflight",
    "plan_digest",
    "scan_cartridge_tree",
]
