"""Decide what has to happen to bring one USB drive and its NAS folder in sync.

Every path is judged three ways: what is on the NAS (N), what is on the USB
drive (U), and what both held at the last verified sync (R, the drive record).

Policy (see docs/LOADMASTER.md):

* The USB drive **mirrors the NAS**. Files new or changed on the NAS are copied
  to USB; files removed from the NAS are removed from USB.
* Files new on the USB drive are **brought to the NAS**.
* When both sides hold different versions, the side that changed since the
  last sync wins; if both changed (or there is no record yet), the **newest**
  modification time wins. Equal times with different sizes are a conflict.
* A video removed from the USB drive whose folder gained a new, unknown video
  is treated as **replaced on the laptop**: the new file comes to the NAS and
  the old NAS file is retired. Any other file missing from USB is restored.
* Loadmaster **never destroys NAS data**. Anything it would overwrite or
  retire on the NAS is moved to ``.loadmaster-replaced`` inside that folder.
* Unusually large removals need confirmation in TruePanel, and a NAS folder
  that suddenly looks empty stops everything.
* exFAT, FAT and NTFS drives treat ``1x05.mkv`` and ``1X05.mkv`` as one name.
  On those drives paths are matched ignoring case and judged under the NAS
  spelling; actions carry the drive's own spelling in ``usb_path``. A NAS
  rename that only changes case is not a new file.
* **Protected folders** (per drive) are never changed on either side: a file
  is only copied to a side that lacks it. Anything else Loadmaster would do
  there is reported as a PROTECTED notice instead.

The plan is a pure function of the three listings, so it is fully testable,
and its digest lets a later run prove nothing changed since it was approved.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from typing import Any

from .scan import MTIME_TOLERANCE_NS, Fingerprint

TO_USB = "to_usb"
TO_NAS = "to_nas"
DELETE_USB = "delete_usb"
RETIRE_NAS = "retire_nas"

# The only actions allowed inside a protected folder: fill a gap on the drive.
PROTECTED_ALLOWED = frozenset({(TO_USB, "NEW_ON_NAS"), (TO_USB, "MISSING_ON_USB")})

# Order of execution: free USB space first, copy, then retire NAS originals.
OP_ORDER = {DELETE_USB: 0, TO_USB: 1, TO_NAS: 2, RETIRE_NAS: 3}

VIDEO_SUFFIXES = frozenset(
    {".mkv", ".mp4", ".m4v", ".avi", ".mov", ".ts", ".m2ts", ".wmv", ".mpg", ".webm"}
)
# Characters exFAT, FAT and NTFS cannot store in a filename.
WINDOWS_ILLEGAL = frozenset('<>:"|?*\\')
WINDOWS_FILESYSTEMS = frozenset({"exfat", "vfat", "ntfs", "ntfs3", "fuseblk"})


@dataclass(frozen=True)
class Action:
    op: str
    path: str
    size: int
    mtime_ns: int
    reason: str
    # The drive's spelling when it differs from ``path`` only in case.
    usb_path: str | None = None


_EPISODE = re.compile(r"[Ss](\d{1,2})[Ee](\d{1,3})")


def _episode(path: str) -> tuple[int, int] | None:
    match = _EPISODE.search(PurePosixPath(path).name)
    return (int(match.group(1)), int(match.group(2))) if match else None


def _video(path: str) -> bool:
    return PurePosixPath(path).suffix.lower() in VIDEO_SUFFIXES


def _folder(path: str) -> str:
    return str(PurePosixPath(path).parent)


def _windows(fstype: str | None) -> bool:
    return (fstype or "").lower() in WINDOWS_FILESYSTEMS


def _storable(path: str, fstype: str | None) -> bool:
    if not _windows(fstype):
        return True
    return not any(ch in WINDOWS_ILLEGAL for ch in path.replace("/", ""))


def _respell(
    files: dict[str, Fingerprint], spelling: dict[str, str]
) -> tuple[dict[str, Fingerprint], dict[str, str]]:
    """Key ``files`` by ``spelling`` (lower-cased path -> preferred path).

    Returns the re-keyed listing and {preferred: original} for every path
    whose spelling changed.
    """

    out: dict[str, Fingerprint] = {}
    changed: dict[str, str] = {}
    for path, fp in files.items():
        preferred = spelling.get(path.lower(), path)
        if preferred in out:
            preferred = path  # a case-sensitive listing with both; leave as is
        out[preferred] = fp
        if preferred != path:
            changed[preferred] = path
    return out, changed


def digest(drive_name: str, actions: list[Action]) -> str:
    material = json.dumps(
        {"drive": drive_name, "actions": [asdict(a) for a in actions]},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode()).hexdigest()


def build_plan(
    *,
    drive_name: str,
    nas: dict[str, Fingerprint],
    usb: dict[str, Fingerprint],
    record: dict[str, Fingerprint] | None,
    usb_fstype: str | None = None,
    large_delete_files: int = 100,
    protected: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Return the sync plan for one drive.

    ``record`` is ``None`` before the first completed sync. Without it nothing
    is ever deleted: every file is simply copied to whichever side lacks it.
    """

    known = record is not None
    record = record or {}
    actions: list[Action] = []
    conflicts: list[dict[str, Any]] = []
    notices: list[dict[str, Any]] = []
    in_sync: dict[str, Fingerprint] = {}
    forget: list[str] = []

    # On a drive that ignores case, judge every path under one spelling: the
    # NAS's, else the record's. usb_spelling maps it back to the drive's name.
    usb_spelling: dict[str, str] = {}
    collides: set[str] = set()
    if _windows(usb_fstype):
        spelling: dict[str, str] = {}
        for path in sorted(nas):
            if path.lower() in spelling:
                collides.add(path)  # a second NAS name for one drive name
            else:
                spelling[path.lower()] = path
        for path in sorted(record):
            spelling.setdefault(path.lower(), path)
        usb, usb_spelling = _respell(usb, spelling)
        record, record_spelling = _respell(record, spelling)
        forget.extend(record_spelling.values())  # stored again under the new name

    guarded = tuple(folder.lower().rstrip("/") + "/" for folder in protected)

    def add(op: str, path: str, fp: Fingerprint, reason: str) -> None:
        if (op, reason) not in PROTECTED_ALLOWED and path.lower().startswith(guarded):
            notices.append(
                {"path": path, "reason": "PROTECTED", "would": f"{op} {reason}"}
            )
            return
        if op == TO_USB and not _storable(path, usb_fstype):
            notices.append({"path": path, "reason": "NAME_NOT_STORABLE_ON_USB"})
            return
        if op == TO_USB and path in collides:
            notices.append({"path": path, "reason": "NAME_DIFFERS_ONLY_BY_CASE_ON_NAS"})
            return
        actions.append(
            Action(op, path, fp.size, fp.mtime_ns, reason, usb_spelling.get(path))
        )

    # Videos on USB that nobody has seen before, by folder and episode. A video
    # deleted from USB with a new counterpart here (same episode for TV, any
    # video for a movie folder) was upgraded on the laptop.
    new_usb_videos = {
        (_folder(path), _episode(path))
        for path in usb
        if _video(path) and path not in nas and path not in record
    }

    def replaced_on_usb(path: str) -> bool:
        return _video(path) and (_folder(path), _episode(path)) in new_usb_videos

    for path in sorted(set(nas) | set(usb) | set(record)):
        n, u, r = nas.get(path), usb.get(path), record.get(path)

        if n and u:
            if n.same_as(u):
                in_sync[path] = n
                if path in usb_spelling:
                    notices.append(
                        {
                            "path": path,
                            "reason": "CASE_DIFFERS_ON_USB",
                            "usb_path": usb_spelling[path],
                        }
                    )
                continue
            nas_changed = not n.same_as(r)
            usb_changed = not u.same_as(r)
            if nas_changed and not usb_changed:
                add(TO_USB, path, n, "UPDATED_ON_NAS")
            elif usb_changed and not nas_changed:
                add(TO_NAS, path, u, "UPDATED_ON_USB")
            elif abs(n.mtime_ns - u.mtime_ns) <= MTIME_TOLERANCE_NS:
                conflicts.append(
                    {
                        "path": path,
                        "reason": "SAME_AGE_DIFFERENT_SIZE",
                        "nas": asdict(n),
                        "usb": asdict(u),
                    }
                )
            elif n.mtime_ns > u.mtime_ns:
                add(TO_USB, path, n, "NEWER_ON_NAS")
            else:
                add(TO_NAS, path, u, "NEWER_ON_USB")

        elif n:
            if r is None:
                add(TO_USB, path, n, "NEW_ON_NAS")
            elif not n.same_as(r):
                add(TO_USB, path, n, "UPDATED_ON_NAS")
            elif replaced_on_usb(path):
                add(RETIRE_NAS, path, n, "REPLACED_ON_USB")
            else:
                add(TO_USB, path, n, "MISSING_ON_USB")

        elif u:
            if r is None:
                add(TO_NAS, path, u, "NEW_ON_USB")
            elif u.same_as(r):
                add(DELETE_USB, path, u, "REMOVED_FROM_NAS")
            else:
                add(TO_NAS, path, u, "UPDATED_ON_USB_AFTER_NAS_REMOVAL")

        else:
            forget.append(path)  # gone from both sides

    actions.sort(key=lambda a: (OP_ORDER[a.op], a.path))

    removals = [a for a in actions if a.op in {DELETE_USB, RETIRE_NAS}]
    needs_confirmation = len(removals) > large_delete_files
    hold_reason = None

    if conflicts:
        hold_reason = f"{len(conflicts)} conflict(s) need a decision"
    elif known and record and not nas:
        # The NAS folder looks empty but files were synced before: almost
        # certainly an unmounted dataset, never a real mass deletion.
        hold_reason = "NAS folder is empty; is the pool mounted?"
        actions = []

    state = "HOLD" if hold_reason else "READY" if actions else "CLEAR"

    def total(op: str) -> tuple[int, int]:
        chosen = [a for a in actions if a.op == op]
        return len(chosen), sum(a.size for a in chosen)

    to_usb, to_usb_bytes = total(TO_USB)
    to_nas, to_nas_bytes = total(TO_NAS)
    deletes, delete_bytes = total(DELETE_USB)
    retires, _ = total(RETIRE_NAS)

    return {
        "drive": drive_name,
        "state": state,
        "reason": hold_reason,
        "first_sync": not known,
        "needs_confirmation": needs_confirmation and state == "READY",
        "summary": {
            "to_usb_files": to_usb,
            "to_usb_bytes": to_usb_bytes,
            "to_nas_files": to_nas,
            "to_nas_bytes": to_nas_bytes,
            "delete_usb_files": deletes,
            "delete_usb_bytes": delete_bytes,
            "retire_nas_files": retires,
            "in_sync_files": len(in_sync),
            "conflicts": len(conflicts),
            "notices": len(notices),
        },
        "actions": [asdict(a) for a in actions],
        "conflicts": conflicts,
        "notices": notices,
        "in_sync": {path: fp.to_list() for path, fp in in_sync.items()},
        "forget": forget,
        "digest": digest(drive_name, actions),
    }


def pending_to_usb(
    nas: dict[str, Fingerprint], record: dict[str, Fingerprint]
) -> tuple[int, int]:
    """What would go NAS -> USB next time, judged without the drive present."""

    files = [fp for path, fp in nas.items() if not fp.same_as(record.get(path))]
    return len(files), sum(fp.size for fp in files)


__all__ = [
    "Action",
    "DELETE_USB",
    "RETIRE_NAS",
    "TO_NAS",
    "TO_USB",
    "build_plan",
    "digest",
    "pending_to_usb",
]
