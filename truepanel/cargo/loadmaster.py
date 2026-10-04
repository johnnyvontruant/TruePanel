"""Fail-closed Loadmaster transfer planning.

The planner is intentionally non-actuating. It compares one approved removable
cartridge with its canonical NAS scope and produces explicit copy or HOLD
actions. It never deletes media and never resolves ambiguous conflicts by
timestamp alone.

A successful executor can persist an inventory snapshot after verification.
That snapshot lets later plans distinguish a file changed on one side from two
independently changed files.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .cartridges import CartridgeDefinition

LOADMASTER_INVENTORY_SCHEMA_VERSION = 1
LOADMASTER_INVENTORY_KIND = "truepanel.loadmaster_inventory"
DEFAULT_MTIME_TOLERANCE_SECONDS = 2.0
DEFAULT_IGNORED_NAMES = frozenset(
    {
        ".DS_Store",
        ".Spotlight-V100",
        ".Trashes",
        ".fseventsd",
        "System Volume Information",
    }
)
SDR_RESCUE_IGNORED_MARKERS = (
    ".sdr-rescue-backup-",
)
SDR_RESCUE_IGNORED_SUFFIXES = (
    ".sdr-rescue-partial",
    ".failed-sdr-rescue",
)


class LoadmasterPlanError(RuntimeError):
    """Fail-closed planning error."""


@dataclass(frozen=True)
class FileFingerprint:
    size_bytes: int
    mtime_ns: int

    @classmethod
    def from_stat(
        cls,
        value: os.stat_result,
    ) -> "FileFingerprint":
        return cls(
            size_bytes=int(value.st_size),
            mtime_ns=int(value.st_mtime_ns),
        )

    @classmethod
    def from_dict(
        cls,
        value: dict[str, Any],
    ) -> "FileFingerprint":
        size = value.get("size_bytes")
        mtime = value.get("mtime_ns")

        if (
            isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
        ):
            raise ValueError(
                "inventory size_bytes is invalid"
            )

        if (
            isinstance(mtime, bool)
            or not isinstance(mtime, int)
            or mtime < 0
        ):
            raise ValueError(
                "inventory mtime_ns is invalid"
            )

        return cls(
            size_bytes=size,
            mtime_ns=mtime,
        )


@dataclass(frozen=True)
class LoadmasterAction:
    direction: str
    relative_path: str
    size_bytes: int
    reason: str


@dataclass(frozen=True)
class LoadmasterConflict:
    relative_path: str
    reason: str
    nas: FileFingerprint | None
    usb: FileFingerprint | None
    baseline: FileFingerprint | None


def _fingerprints_match(
    left: FileFingerprint,
    right: FileFingerprint,
    *,
    tolerance_seconds: float,
) -> bool:
    if left.size_bytes != right.size_bytes:
        return False

    tolerance_ns = max(
        0,
        int(
            float(tolerance_seconds)
            * 1_000_000_000
        ),
    )

    return (
        abs(left.mtime_ns - right.mtime_ns)
        <= tolerance_ns
    )


def _ignored_name(
    name: str,
    ignored_names: frozenset[str],
) -> bool:
    if name in ignored_names:
        return True

    if any(
        marker in name
        for marker in SDR_RESCUE_IGNORED_MARKERS
    ):
        return True

    return name.endswith(
        SDR_RESCUE_IGNORED_SUFFIXES
    )


def scan_tree(
    root: Path,
    *,
    ignored_names: frozenset[str] = (
        DEFAULT_IGNORED_NAMES
    ),
) -> dict[str, FileFingerprint]:
    """Return regular files under root without following symlinks."""

    if not root.is_absolute():
        raise LoadmasterPlanError(
            "scan root must be absolute"
        )

    try:
        root_info = root.lstat()
    except FileNotFoundError as error:
        raise LoadmasterPlanError(
            f"scan root does not exist: {root}"
        ) from error

    if stat.S_ISLNK(root_info.st_mode):
        raise LoadmasterPlanError(
            f"scan root is a symlink: {root}"
        )

    if not stat.S_ISDIR(root_info.st_mode):
        raise LoadmasterPlanError(
            f"scan root is not a directory: {root}"
        )

    result: dict[
        str,
        FileFingerprint,
    ] = {}

    for current, dirs, files in os.walk(
        root,
        topdown=True,
        followlinks=False,
    ):
        current_path = Path(current)
        kept_dirs = []

        for name in dirs:
            if _ignored_name(
                name,
                ignored_names,
            ):
                continue

            candidate = current_path / name

            try:
                info = candidate.lstat()
            except OSError as error:
                raise LoadmasterPlanError(
                    "directory unreadable: "
                    f"{candidate}: {error}"
                ) from error

            if stat.S_ISLNK(info.st_mode):
                raise LoadmasterPlanError(
                    "symlink directory is not "
                    f"allowed: {candidate}"
                )

            if not stat.S_ISDIR(info.st_mode):
                raise LoadmasterPlanError(
                    "unexpected non-directory "
                    f"entry: {candidate}"
                )

            kept_dirs.append(name)

        dirs[:] = kept_dirs

        for name in files:
            if _ignored_name(
                name,
                ignored_names,
            ):
                continue

            candidate = current_path / name

            try:
                info = candidate.lstat()
            except OSError as error:
                raise LoadmasterPlanError(
                    "file unreadable: "
                    f"{candidate}: {error}"
                ) from error

            if stat.S_ISLNK(info.st_mode):
                raise LoadmasterPlanError(
                    "symlink file is not allowed: "
                    f"{candidate}"
                )

            if not stat.S_ISREG(info.st_mode):
                raise LoadmasterPlanError(
                    "non-regular file is not "
                    f"allowed: {candidate}"
                )

            relative = (
                candidate
                .relative_to(root)
                .as_posix()
            )

            result[relative] = (
                FileFingerprint.from_stat(
                    info
                )
            )

    return result


def load_inventory(
    path: Path | None,
    *,
    cartridge_id: str,
) -> dict[str, FileFingerprint]:
    """Load a previous verified inventory, or an empty baseline."""

    if path is None or not path.exists():
        return {}

    try:
        payload = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ) as error:
        raise LoadmasterPlanError(
            "invalid Loadmaster inventory: "
            f"{error}"
        ) from error

    if not isinstance(payload, dict):
        raise LoadmasterPlanError(
            "Loadmaster inventory must be an object"
        )

    if (
        payload.get("schema_version")
        != LOADMASTER_INVENTORY_SCHEMA_VERSION
    ):
        raise LoadmasterPlanError(
            "unsupported Loadmaster inventory schema"
        )

    if (
        payload.get("kind")
        != LOADMASTER_INVENTORY_KIND
    ):
        raise LoadmasterPlanError(
            "Loadmaster inventory kind is invalid"
        )

    if (
        str(payload.get("cartridge_id") or "")
        != cartridge_id
    ):
        raise LoadmasterPlanError(
            "Loadmaster inventory cartridge id mismatch"
        )

    items = payload.get("items")

    if not isinstance(items, dict):
        raise LoadmasterPlanError(
            "Loadmaster inventory items must be an object"
        )

    result: dict[
        str,
        FileFingerprint,
    ] = {}

    for relative, raw in items.items():
        if (
            not isinstance(relative, str)
            or not relative
            or relative.startswith("/")
            or ".." in Path(relative).parts
        ):
            raise LoadmasterPlanError(
                "Loadmaster inventory relative "
                "path is invalid"
            )

        if not isinstance(raw, dict):
            raise LoadmasterPlanError(
                "Loadmaster inventory entry is "
                f"invalid: {relative}"
            )

        try:
            result[relative] = (
                FileFingerprint.from_dict(
                    raw
                )
            )
        except ValueError as error:
            raise LoadmasterPlanError(
                "Loadmaster inventory entry is "
                f"invalid: {relative}: {error}"
            ) from error

    return result


def build_sync_plan(
    *,
    cartridge: CartridgeDefinition,
    usb_mount: Path,
    inventory: (
        dict[str, FileFingerprint]
        | None
    ) = None,
    tolerance_seconds: float = (
        DEFAULT_MTIME_TOLERANCE_SECONDS
    ),
) -> dict[str, Any]:
    """Build a non-actuating, no-delete transfer plan."""

    if not usb_mount.is_absolute():
        raise LoadmasterPlanError(
            "USB mount path must be absolute"
        )

    nas_root = cartridge.source_prefix
    usb_root = (
        usb_mount
        / cartridge.usb_relative_path
    )

    nas = scan_tree(nas_root)
    usb = scan_tree(usb_root)
    baseline = inventory or {}

    actions: list[
        LoadmasterAction
    ] = []

    conflicts: list[
        LoadmasterConflict
    ] = []

    unchanged = 0

    all_paths = sorted(
        set(nas)
        | set(usb)
        | set(baseline)
    )

    for relative in all_paths:
        nas_fp = nas.get(relative)
        usb_fp = usb.get(relative)
        old_fp = baseline.get(relative)

        if (
            nas_fp is not None
            and usb_fp is not None
        ):
            if _fingerprints_match(
                nas_fp,
                usb_fp,
                tolerance_seconds=(
                    tolerance_seconds
                ),
            ):
                unchanged += 1
                continue

            if old_fp is None:
                conflicts.append(
                    LoadmasterConflict(
                        relative_path=relative,
                        reason=(
                            "DIVERGENT_WITHOUT_BASELINE"
                        ),
                        nas=nas_fp,
                        usb=usb_fp,
                        baseline=None,
                    )
                )
                continue

            nas_unchanged = (
                _fingerprints_match(
                    nas_fp,
                    old_fp,
                    tolerance_seconds=(
                        tolerance_seconds
                    ),
                )
            )

            usb_unchanged = (
                _fingerprints_match(
                    usb_fp,
                    old_fp,
                    tolerance_seconds=(
                        tolerance_seconds
                    ),
                )
            )

            if (
                nas_unchanged
                and not usb_unchanged
            ):
                if cartridge.allow_ingest:
                    actions.append(
                        LoadmasterAction(
                            direction=(
                                "USB_TO_NAS"
                            ),
                            relative_path=(
                                relative
                            ),
                            size_bytes=(
                                usb_fp.size_bytes
                            ),
                            reason="USB_UPDATED",
                        )
                    )
                else:
                    conflicts.append(
                        LoadmasterConflict(
                            relative_path=(
                                relative
                            ),
                            reason=(
                                "INGEST_DISABLED"
                            ),
                            nas=nas_fp,
                            usb=usb_fp,
                            baseline=old_fp,
                        )
                    )

                continue

            if (
                usb_unchanged
                and not nas_unchanged
            ):
                if cartridge.allow_backup:
                    actions.append(
                        LoadmasterAction(
                            direction=(
                                "NAS_TO_USB"
                            ),
                            relative_path=(
                                relative
                            ),
                            size_bytes=(
                                nas_fp.size_bytes
                            ),
                            reason="NAS_UPDATED",
                        )
                    )
                else:
                    conflicts.append(
                        LoadmasterConflict(
                            relative_path=(
                                relative
                            ),
                            reason=(
                                "BACKUP_DISABLED"
                            ),
                            nas=nas_fp,
                            usb=usb_fp,
                            baseline=old_fp,
                        )
                    )

                continue

            conflicts.append(
                LoadmasterConflict(
                    relative_path=relative,
                    reason="BOTH_SIDES_CHANGED",
                    nas=nas_fp,
                    usb=usb_fp,
                    baseline=old_fp,
                )
            )
            continue

        if (
            nas_fp is not None
            and usb_fp is None
        ):
            reason = (
                "MISSING_ON_USB"
                if old_fp is not None
                else "NEW_ON_NAS"
            )

            if cartridge.allow_backup:
                actions.append(
                    LoadmasterAction(
                        direction="NAS_TO_USB",
                        relative_path=relative,
                        size_bytes=(
                            nas_fp.size_bytes
                        ),
                        reason=reason,
                    )
                )
            else:
                conflicts.append(
                    LoadmasterConflict(
                        relative_path=relative,
                        reason="BACKUP_DISABLED",
                        nas=nas_fp,
                        usb=None,
                        baseline=old_fp,
                    )
                )

            continue

        if (
            usb_fp is not None
            and nas_fp is None
        ):
            if old_fp is not None:
                conflicts.append(
                    LoadmasterConflict(
                        relative_path=relative,
                        reason=(
                            "MISSING_ON_NAS_"
                            "SINCE_LAST_SYNC"
                        ),
                        nas=None,
                        usb=usb_fp,
                        baseline=old_fp,
                    )
                )
                continue

            if cartridge.allow_ingest:
                actions.append(
                    LoadmasterAction(
                        direction="USB_TO_NAS",
                        relative_path=relative,
                        size_bytes=(
                            usb_fp.size_bytes
                        ),
                        reason="NEW_ON_USB",
                    )
                )
            else:
                conflicts.append(
                    LoadmasterConflict(
                        relative_path=relative,
                        reason="INGEST_DISABLED",
                        nas=None,
                        usb=usb_fp,
                        baseline=None,
                    )
                )

            continue

        if old_fp is not None:
            conflicts.append(
                LoadmasterConflict(
                    relative_path=relative,
                    reason="MISSING_ON_BOTH_SIDES",
                    nas=None,
                    usb=None,
                    baseline=old_fp,
                )
            )

    ingest = [
        action
        for action in actions
        if action.direction == "USB_TO_NAS"
    ]

    backup = [
        action
        for action in actions
        if action.direction == "NAS_TO_USB"
    ]

    state = (
        "HOLD"
        if conflicts
        else "READY"
        if actions
        else "CLEAR"
    )

    return {
        "schema_version": 1,
        "read_only": True,
        "delete_policy": "never",
        "state": state,
        "cartridge": (
            cartridge.public_dict()
        ),
        "nas_root": str(nas_root),
        "usb_root": str(usb_root),
        "summary": {
            "ingest_files": len(ingest),
            "ingest_bytes": sum(
                item.size_bytes
                for item in ingest
            ),
            "backup_files": len(backup),
            "backup_bytes": sum(
                item.size_bytes
                for item in backup
            ),
            "unchanged_files": unchanged,
            "conflicts": len(conflicts),
        },
        "actions": [
            asdict(action)
            for action in actions
        ],
        "conflicts": [
            {
                "relative_path": (
                    item.relative_path
                ),
                "reason": item.reason,
                "nas": (
                    asdict(item.nas)
                    if item.nas
                    else None
                ),
                "usb": (
                    asdict(item.usb)
                    if item.usb
                    else None
                ),
                "baseline": (
                    asdict(item.baseline)
                    if item.baseline
                    else None
                ),
            }
            for item in conflicts
        ],
    }


def _regular_file_fingerprint(
    path: Path,
) -> FileFingerprint | None:
    """Inspect one optional regular file without following symlinks."""

    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as error:
        raise LoadmasterPlanError(
            f"file unreadable: {path}: {error}"
        ) from error

    if stat.S_ISLNK(info.st_mode):
        raise LoadmasterPlanError(
            f"symlink file is not allowed: {path}"
        )

    if not stat.S_ISREG(info.st_mode):
        raise LoadmasterPlanError(
            f"non-regular file is not allowed: {path}"
        )

    return FileFingerprint.from_stat(info)


def _validate_existing_directory_chain(
    root: Path,
    parent: Path,
) -> None:
    """Reject symlink or non-directory ancestors under one trusted root."""

    try:
        relative = parent.relative_to(root)
    except ValueError as error:
        raise LoadmasterPlanError(
            f"destination escaped USB root: {parent}"
        ) from error

    current = root

    for part in relative.parts:
        current = current / part

        try:
            info = current.lstat()
        except FileNotFoundError:
            return
        except OSError as error:
            raise LoadmasterPlanError(
                f"directory unreadable: {current}: {error}"
            ) from error

        if stat.S_ISLNK(info.st_mode):
            raise LoadmasterPlanError(
                f"symlink directory is not allowed: {current}"
            )

        if not stat.S_ISDIR(info.st_mode):
            raise LoadmasterPlanError(
                f"unexpected non-directory entry: {current}"
            )


def build_backlog_backup_plan(
    *,
    cartridge: CartridgeDefinition,
    usb_mount: Path,
    backlog_items: list[dict[str, Any]],
    inventory: (
        dict[str, FileFingerprint]
        | None
    ) = None,
    tolerance_seconds: float = (
        DEFAULT_MTIME_TOLERANCE_SECONDS
    ),
) -> dict[str, Any]:
    """Plan NAS-to-USB work only for durable Loadmaster backlog items.

    Unlike the full sync planner, this intentionally does not scan unrelated
    USB files. Pre-existing cartridge-only files therefore cannot turn a
    backup run into accidental ingest work.
    """

    if not usb_mount.is_absolute():
        raise LoadmasterPlanError(
            "USB mount path must be absolute"
        )

    nas_root = cartridge.source_prefix
    usb_root = (
        usb_mount
        / cartridge.usb_relative_path
    )
    baseline = inventory or {}

    if not usb_root.is_dir():
        raise LoadmasterPlanError(
            f"USB cartridge root is unavailable: {usb_root}"
        )

    actions: list[LoadmasterAction] = []
    conflicts: list[LoadmasterConflict] = []
    unchanged = 0
    seen: set[str] = set()

    for item in backlog_items:
        if not isinstance(item, dict):
            raise LoadmasterPlanError(
                "Loadmaster backlog item must be an object"
            )

        source_text = str(
            item.get("current_path")
            or ""
        ).strip()
        source = Path(source_text)

        if (
            not source.is_absolute()
            or ".." in source.parts
        ):
            raise LoadmasterPlanError(
                "Loadmaster backlog path is invalid"
            )

        try:
            relative_path = source.relative_to(
                nas_root
            )
        except ValueError as error:
            raise LoadmasterPlanError(
                "Loadmaster backlog path is outside "
                f"cartridge scope: {source}"
            ) from error

        relative = relative_path.as_posix()

        if relative in seen:
            raise LoadmasterPlanError(
                f"duplicate Loadmaster backlog path: {relative}"
            )
        seen.add(relative)

        source_fp = _regular_file_fingerprint(
            source
        )

        if source_fp is None:
            raise LoadmasterPlanError(
                f"Loadmaster source is unavailable: {source}"
            )

        expected_size = item.get(
            "size_bytes"
        )

        if (
            isinstance(expected_size, bool)
            or not isinstance(
                expected_size,
                int,
            )
            or expected_size < 0
        ):
            raise LoadmasterPlanError(
                f"Loadmaster backlog size is invalid: {source}"
            )

        if source_fp.size_bytes != expected_size:
            raise LoadmasterPlanError(
                "Loadmaster source size no longer "
                f"matches backlog: {source}"
            )

        destination = (
            usb_root
            / relative_path
        )

        _validate_existing_directory_chain(
            usb_root,
            destination.parent,
        )

        usb_fp = _regular_file_fingerprint(
            destination
        )
        old_fp = baseline.get(relative)

        if (
            usb_fp is not None
            and _fingerprints_match(
                source_fp,
                usb_fp,
                tolerance_seconds=(
                    tolerance_seconds
                ),
            )
        ):
            unchanged += 1
            continue

        if usb_fp is None:
            actions.append(
                LoadmasterAction(
                    direction="NAS_TO_USB",
                    relative_path=relative,
                    size_bytes=(
                        source_fp.size_bytes
                    ),
                    reason=(
                        "MISSING_ON_USB"
                        if old_fp is not None
                        else "NEW_ON_NAS"
                    ),
                )
            )
            continue

        if old_fp is None:
            conflicts.append(
                LoadmasterConflict(
                    relative_path=relative,
                    reason=(
                        "USB_DESTINATION_WITHOUT_BASELINE"
                    ),
                    nas=source_fp,
                    usb=usb_fp,
                    baseline=None,
                )
            )
            continue

        if not _fingerprints_match(
            usb_fp,
            old_fp,
            tolerance_seconds=(
                tolerance_seconds
            ),
        ):
            conflicts.append(
                LoadmasterConflict(
                    relative_path=relative,
                    reason=(
                        "USB_CHANGED_SINCE_BASELINE"
                    ),
                    nas=source_fp,
                    usb=usb_fp,
                    baseline=old_fp,
                )
            )
            continue

        actions.append(
            LoadmasterAction(
                direction="NAS_TO_USB",
                relative_path=relative,
                size_bytes=(
                    source_fp.size_bytes
                ),
                reason="BACKLOG_UPDATED",
            )
        )

    state = (
        "HOLD"
        if conflicts
        else "READY"
        if actions
        else "CLEAR"
    )

    return {
        "schema_version": 1,
        "read_only": True,
        "delete_policy": "never",
        "scope": "durable_backlog",
        "state": state,
        "cartridge": (
            cartridge.public_dict()
        ),
        "nas_root": str(nas_root),
        "usb_root": str(usb_root),
        "summary": {
            "scoped_items": len(
                backlog_items
            ),
            "ingest_files": 0,
            "ingest_bytes": 0,
            "backup_files": len(
                actions
            ),
            "backup_bytes": sum(
                item.size_bytes
                for item in actions
            ),
            "unchanged_files": unchanged,
            "conflicts": len(
                conflicts
            ),
        },
        "actions": [
            asdict(action)
            for action in actions
        ],
        "conflicts": [
            {
                "relative_path": (
                    item.relative_path
                ),
                "reason": item.reason,
                "nas": (
                    asdict(item.nas)
                    if item.nas
                    else None
                ),
                "usb": (
                    asdict(item.usb)
                    if item.usb
                    else None
                ),
                "baseline": (
                    asdict(item.baseline)
                    if item.baseline
                    else None
                ),
            }
            for item in conflicts
        ],
    }


def inventory_payload(
    *,
    cartridge: CartridgeDefinition,
    files: dict[str, FileFingerprint],
    captured_at: str,
) -> dict[str, Any]:
    """Build durable inventory after an executor verifies sync."""

    return {
        "schema_version": (
            LOADMASTER_INVENTORY_SCHEMA_VERSION
        ),
        "kind": LOADMASTER_INVENTORY_KIND,
        "cartridge_id": (
            cartridge.cartridge_id
        ),
        "captured_at": str(captured_at),
        "items": {
            path: asdict(fingerprint)
            for path, fingerprint
            in sorted(files.items())
        },
    }
