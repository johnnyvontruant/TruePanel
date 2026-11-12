"""Recognise the same movie or show under a different folder name.

Old copies on a drive often sit in a folder that no longer matches the NAS:
Radarr renamed it ("Hail Caesar (2016)" -> "Hail, Caesar (2016)"), the words
moved ("Book of Shadows Blair Witch 2" -> "Blair Witch 2 - Book of Shadows"),
or the movie was filed on the wrong drive. Comparing folder names exactly
misses all of these, so a top-level folder gets identity keys:

* ``tmdb:<id>`` from the ``.media-identity.json`` the library keeps beside
  each movie (most reliable);
* ``title:<words>|<year>``: the folder name's words, lower-cased, without
  punctuation, articles or word order, plus its year. Folders without a year
  get no title key, so generic names never match.

``library_index`` maps every key to the NAS folders that carry it, across all
configured drives. Reading is all this module does.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable
from pathlib import Path

from .scan import ignored

IDENTITY_FILE = ".media-identity.json"
_YEAR = re.compile(r"\((\d{4})\)")
_ARTICLES = frozenset({"the", "a", "an"})

# key -> [(drive name, folder name)]
Library = dict[str, list[tuple[str, str]]]


def title_key(folder: str) -> str | None:
    match = _YEAR.search(folder)
    if not match:
        return None
    text = _YEAR.sub(" ", folder).lower().replace("'", "").replace("’", "")
    words = re.findall(r"[a-z0-9]+", text)
    words = sorted(w for w in words if w not in _ARTICLES)
    return f"title:{' '.join(words)}|{match.group(1)}" if words else None


def tmdb_key(folder_path: Path) -> str | None:
    try:
        payload = json.loads((folder_path / IDENTITY_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    tmdb = payload.get("tmdb_id") if isinstance(payload, dict) else None
    return f"tmdb:{tmdb}" if isinstance(tmdb, int) and tmdb > 0 else None


def folder_keys(root: Path) -> dict[str, set[str]]:
    """Identity keys of every top-level folder under ``root``."""

    keys: dict[str, set[str]] = {}
    try:
        entries = list(os.scandir(root))
    except OSError:
        return keys
    for entry in entries:
        if ignored(entry.name) or not entry.is_dir(follow_symlinks=False):
            continue
        found = {k for k in (title_key(entry.name), tmdb_key(Path(entry.path))) if k}
        if found:
            keys[entry.name] = found
    return keys


def library_index(drives: Iterable[tuple[str, Path]]) -> Library:
    """Every identity key on the NAS, for (drive name, NAS folder) pairs."""

    library: Library = {}
    for name, nas_path in drives:
        for folder, found in folder_keys(nas_path).items():
            for key in found:
                library.setdefault(key, []).append((name, folder))
    return library


__all__ = ["IDENTITY_FILE", "Library", "folder_keys", "library_index", "title_key"]
