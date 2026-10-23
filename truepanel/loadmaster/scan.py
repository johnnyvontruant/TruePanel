"""Walk a media tree and fingerprint every file by size and modification time.

Hidden names (starting with ``.``) and operating-system clutter are skipped:
Sonarr, Radarr and Plex ignore them too, and Loadmaster's own partial files
and replaced-file folder are hidden. Symlinks and special files are skipped
and reported rather than followed.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

# Two files are "the same" when sizes match and mtimes are within this window.
# FAT-family drives store times at 2 s resolution.
MTIME_TOLERANCE_NS = 2_000_000_000

CLUTTER = frozenset(
    {
        "$RECYCLE.BIN",
        "System Volume Information",
        "Thumbs.db",
        "desktop.ini",
        "lost+found",
    }
)


class ScanError(RuntimeError):
    """A tree could not be scanned (missing, not a directory, unreadable)."""


@dataclass(frozen=True)
class Fingerprint:
    size: int
    mtime_ns: int

    def same_as(self, other: Fingerprint | None) -> bool:
        return (
            other is not None
            and self.size == other.size
            and abs(self.mtime_ns - other.mtime_ns) <= MTIME_TOLERANCE_NS
        )

    def to_list(self) -> list[int]:
        return [self.size, self.mtime_ns]

    @classmethod
    def from_list(cls, value: list[int]) -> Fingerprint:
        size, mtime = value
        if not isinstance(size, int) or not isinstance(mtime, int) or size < 0:
            raise ValueError("invalid fingerprint")
        return cls(size, mtime)


@dataclass
class Tree:
    files: dict[str, Fingerprint]
    skipped: list[str]

    @property
    def total_bytes(self) -> int:
        return sum(fp.size for fp in self.files.values())


def ignored(name: str) -> bool:
    return name.startswith(".") or name in CLUTTER


def scan(root: Path) -> Tree:
    """Fingerprint regular files under ``root``, keyed by POSIX relative path."""

    try:
        info = root.lstat()
    except FileNotFoundError as error:
        raise ScanError(f"folder not found: {root}") from error
    except OSError as error:
        raise ScanError(f"folder unreadable: {root}: {error}") from error
    if not stat.S_ISDIR(info.st_mode):
        raise ScanError(f"not a folder: {root}")

    files: dict[str, Fingerprint] = {}
    skipped: list[str] = []

    def walk(directory: str, prefix: str) -> None:
        try:
            entries = list(os.scandir(directory))
        except OSError as error:
            raise ScanError(f"folder unreadable: {directory}: {error}") from error
        for entry in entries:
            if ignored(entry.name):
                continue
            relative = f"{prefix}{entry.name}"
            try:
                entry_info = entry.stat(follow_symlinks=False)
            except OSError as error:
                raise ScanError(f"unreadable: {entry.path}: {error}") from error
            if stat.S_ISDIR(entry_info.st_mode):
                walk(entry.path, relative + "/")
            elif stat.S_ISREG(entry_info.st_mode):
                files[relative] = Fingerprint(
                    entry_info.st_size, entry_info.st_mtime_ns
                )
            else:
                skipped.append(relative)

    walk(str(root), "")
    return Tree(files=files, skipped=skipped)


__all__ = ["Fingerprint", "MTIME_TOLERANCE_NS", "ScanError", "Tree", "ignored", "scan"]
