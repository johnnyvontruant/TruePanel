"""Which commit a TruePanel tree was built from.

The package version (``1.3.1rc1``) stays the same across many upgrades, so it
cannot tell which code is deployed. Staging an upgrade writes
``truepanel-build.json`` (commit, branch, commit date, whether the source
checkout had uncommitted changes) into the stage, promotion carries it into
the deployment, and ``truepanel version`` / ``verify`` report it.
"""

from __future__ import annotations

import json
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


def write_build(root: Path, source: Path) -> dict[str, Any]:
    build = source_build(source)
    if build:
        build["staged_at"] = datetime.now(UTC).isoformat()
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


__all__ = ["BUILD_FILE", "describe", "read_build", "source_build", "write_build"]
