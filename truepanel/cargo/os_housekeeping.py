"""Conservative cross-platform housekeeping exclusion policy for Loadmaster.

Filters known OS metadata by exact filename/directory or narrow thumbnail
cache pattern. No broad dotfile, Windows hidden-attribute or media extension
exclusion. Skipping a file is never permission to delete it.
"""
from __future__ import annotations

from pathlib import PurePosixPath

# Directory names can occur anywhere beneath a cartridge's media root.
HOUSEKEEPING_DIRECTORIES = frozenset({
    # macOS indexing, metadata, Trash and extraction containers.
    ".spotlight-v100",
    ".trashes",
    ".fseventsd",
    ".temporaryitems",
    ".documentrevisions-v100",
    ".appledouble",
    ".appledb",
    "__macosx",
    # Windows drive indexing and recycle bins.
    "system volume information",
    "$recycle.bin",
    "recycler",
    "recycled",
    # Our own aborted/partial transfers are not media either.
    ".loadmaster-rsync-stage",
})

HOUSEKEEPING_FILES = frozenset({
    ".ds_store",
    ".localized",
    ".apdisk",
    ".volumeicon.icns",
    ".metadata_never_index",
    ".com.apple.timemachine.supported",
    "desktop.ini",
    "thumbs.db",
    "ehthumbs.db",
    "ehthumbs_vista.db",
})


def ignored_os_name(name: str, *, is_dir: bool = False) -> bool:
    """Match only OS-created housekeeping names, case-insensitively.

    A Windows hidden attribute by itself is NOT grounds for exclusion.
    """
    if not isinstance(name, str) or not name:
        return False
    folded = name.casefold()
    if folded.startswith("._"):  # AppleDouble resource-fork companion
        return True
    if folded in HOUSEKEEPING_DIRECTORIES:
        return True
    if folded in HOUSEKEEPING_FILES:
        return True
    if not is_dir and (folded.startswith("thumbcache_") or
                       folded.startswith("iconcache_")) and folded.endswith(".db"):
        return True
    return False


def ignored_os_path(relative_path: str) -> bool:
    """Check every path component, not just the final media filename."""
    if not isinstance(relative_path, str) or not relative_path:
        return False
    components = PurePosixPath(relative_path).parts
    return any(ignored_os_name(part, is_dir=index < len(components) - 1)
               for index, part in enumerate(components))
