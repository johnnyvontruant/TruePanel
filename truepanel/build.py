"""Which commit a TruePanel tree was built from.

The package version (``1.3.1rc1``) stays the same across many upgrades, so it
cannot tell which code is deployed. Staging an upgrade writes
``truepanel-build.json`` (commit, branch, commit date, whether the source
checkout had uncommitted changes) into the stage, promotion carries it into
the deployment, and ``truepanel version`` / ``verify`` report it.

The stamp also records a SHA-256 of every file promotion installs (the same
files the promotion's excludes let through), so ``verify`` can tell when the
deployment was changed outside the guarded upgrade: files changed, missing
or added by hand since that build.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BUILD_FILE = "truepanel-build.json"


def _git(source: Path, *args: str) -> str | None:
    try:
        done = subprocess.run(
            ["git", "-C", str(source), *args],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip()


def source_build(source: Path) -> dict[str, Any]:
    """Describe the git checkout ``source``; empty if it is not one."""

    commit = _git(source, "rev-parse", "HEAD")
    if not commit:
        return {}
    status = _git(source, "status", "--porcelain", "--untracked-files=no")
    return {
        "commit": commit,
        "branch": _git(source, "rev-parse", "--abbrev-ref", "HEAD") or "",
        "committed_at": _git(source, "log", "-1", "--format=%cI") or "",
        "dirty": bool(status),
    }


def _patterns() -> tuple[str, ...]:
    from truepanel.upgrade.promotion import (
        PROMOTION_DEPLOY_EXCLUDES,
        PROMOTION_EXCLUDES,
    )

    return (*PROMOTION_EXCLUDES, *PROMOTION_DEPLOY_EXCLUDES, BUILD_FILE)


def _excluded(rel: str, is_dir: bool, patterns: tuple[str, ...]) -> bool:
    """rsync-style match: a pattern with an inner "/" matches a path suffix,
    otherwise the last component; a trailing "/" matches directories only."""

    name = rel.rsplit("/", 1)[-1]
    for pattern in patterns:
        body = pattern.rstrip("/")
        if pattern.endswith("/") and not is_dir:
            continue
        if "/" in body:
            if rel == body or rel.endswith("/" + body):
                return True
        elif fnmatch.fnmatchcase(name, body):
            return True
    return False


def tree_digest(root: Path) -> dict[str, str]:
    """SHA-256 of every file promotion would install from ``root``."""

    patterns = _patterns()
    files: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        base = Path(dirpath).relative_to(root).as_posix()
        prefix = "" if base == "." else base + "/"
        kept = []
        for name in sorted(dirnames):
            rel, path = prefix + name, os.path.join(dirpath, name)
            if _excluded(rel, True, patterns):
                continue
            if os.path.islink(path):
                files[rel] = "symlink:" + os.readlink(path)
            else:
                kept.append(name)
        dirnames[:] = kept
        for name in sorted(filenames):
            rel, path = prefix + name, os.path.join(dirpath, name)
            if _excluded(rel, False, patterns):
                continue
            if os.path.islink(path):
                files[rel] = "symlink:" + os.readlink(path)
                continue
            digest = hashlib.sha256()
            with open(path, "rb") as handle:
                for chunk in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(chunk)
            files[rel] = digest.hexdigest()
    return files


def drift(root: Path, build: dict[str, Any] | None) -> dict[str, list[str]] | None:
    """Files changed, missing or extra since ``build``; None if not recorded."""

    recorded = (build or {}).get("files")
    if not isinstance(recorded, dict):
        return None
    now = tree_digest(root)
    return {
        "changed": sorted(p for p in recorded if p in now and now[p] != recorded[p]),
        "missing": sorted(p for p in recorded if p not in now),
        "extra": sorted(p for p in now if p not in recorded),
    }


def write_build(root: Path, source: Path) -> dict[str, Any]:
    build = source_build(source)
    if build:
        build["staged_at"] = datetime.now(UTC).isoformat()
        build["files"] = tree_digest(root)
        (root / BUILD_FILE).write_text(
            json.dumps(build, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return build


def read_build(root: Path) -> dict[str, Any] | None:
    try:
        build = json.loads((root / BUILD_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return build if isinstance(build, dict) and build.get("commit") else None


def describe(build: dict[str, Any] | None) -> str:
    if not build:
        return "not recorded"
    branch = build.get("branch") if build.get("branch") not in ("", "HEAD") else ""
    when = str(build.get("committed_at") or "")[:10]
    detail = ", ".join(part for part in (branch, when) if part)
    text = str(build["commit"])[:7] + (f" ({detail})" if detail else "")
    return text + (" with uncommitted changes" if build.get("dirty") else "")


__all__ = [
    "BUILD_FILE",
    "describe",
    "drift",
    "read_build",
    "source_build",
    "tree_digest",
    "write_build",
]
