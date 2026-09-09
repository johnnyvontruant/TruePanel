"""Read-only, race-aware evidence for an actual validated upgrade stage."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any

from truepanel.upgrade.promotion import MANIFEST_NAME

from .acceptance import semantic_sha256

STAGE_WITNESS_SCHEMA = "truepanel.aegis-stage-witness/v1"
MAX_MANIFEST_BYTES = 128 * 1024
MAX_ENTRIES = 20_000
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_TREE_BYTES = 1024 * 1024 * 1024


def _excluded(relative: str, *, directory: bool) -> bool:
    """Match the payload exclusions used by guarded promotion."""

    parts = relative.split("/")
    name = parts[-1]
    if name in {".git", ".venv", ".pytest_cache", ".ruff_cache", "__pycache__"}:
        return True
    if len(parts) == 1 and name in {
        MANIFEST_NAME,
        "truepanel-backup-receipt.json",
        "truepanel.yaml",
        "bin",
    }:
        return True
    if len(parts) >= 2 and parts[0] == "development" and parts[1] in {
        "logs",
        "backups",
        "firmware",
    }:
        return True
    if name.endswith((".pyc", ".bak")) or ".before-" in name:
        return True
    return name.startswith("truepanel.backup-")


def _identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
    )


def _read_regular(
    path: Path, before: os.stat_result, *, capture: bool = False
) -> tuple[str, int, bytes | None, tuple[int, int, int, int, int]]:
    if before.st_size > MAX_FILE_BYTES:
        raise ValueError("StageFileTooLarge")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if _identity(opened) != _identity(before) or not stat.S_ISREG(opened.st_mode):
            raise ValueError("StageChangedDuringWitness")
        digest = hashlib.sha256()
        captured: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_FILE_BYTES:
                raise ValueError("StageFileTooLarge")
            digest.update(chunk)
            if capture:
                captured.append(chunk)
        after = os.fstat(descriptor)
        if _identity(after) != _identity(opened) or total != opened.st_size:
            raise ValueError("StageChangedDuringWitness")
        return (
            digest.hexdigest(),
            total,
            b"".join(captured) if capture else None,
            _identity(after),
        )
    finally:
        os.close(descriptor)


def _scan_directory(
    root: Path,
    directory: Path,
    entries: list[dict[str, Any]],
    totals: dict[str, int],
    identities: dict[Path, tuple[int, int, int, int, int]],
) -> None:
    before = directory.lstat()
    if not stat.S_ISDIR(before.st_mode):
        raise ValueError("UnsafeStageEntry")
    with os.scandir(directory) as listing:
        children = sorted(listing, key=lambda item: item.name)
    for child in children:
        path = Path(child.path)
        relative = path.relative_to(root).as_posix()
        observed = path.lstat()
        is_directory = stat.S_ISDIR(observed.st_mode)
        if _excluded(relative, directory=is_directory):
            continue
        if stat.S_ISLNK(observed.st_mode):
            raise ValueError("StageSymlinkRejected")
        if is_directory:
            _scan_directory(root, path, entries, totals, identities)
            continue
        if not stat.S_ISREG(observed.st_mode):
            raise ValueError("UnsafeStageEntry")
        digest, size, _, identity = _read_regular(path, observed)
        totals["entries"] += 1
        totals["bytes"] += size
        if totals["entries"] > MAX_ENTRIES or totals["bytes"] > MAX_TREE_BYTES:
            raise ValueError("StageTreeLimitExceeded")
        entries.append(
            {
                "path": relative,
                "mode": stat.S_IMODE(observed.st_mode),
                "size": size,
                "sha256": digest,
            }
        )
        identities[path] = identity
    after = directory.lstat()
    if _identity(after) != _identity(before):
        raise ValueError("StageChangedDuringWitness")


def witness_validated_stage(stage_root: str | Path) -> dict[str, Any]:
    """Return bounded stage evidence without writing or following links."""

    supplied = Path(stage_root)
    result: dict[str, Any] = {
        "schema": STAGE_WITNESS_SCHEMA,
        "status": "HOLD",
        "reason": "StageWitnessUnavailable",
        "stage_tree_sha256": None,
        "manifest_sha256": None,
        "entry_count": 0,
        "total_bytes": 0,
        "manifest": None,
        "filesystem_writes": 0,
        "promotion_performed": False,
        "control_authority": False,
    }
    try:
        if not supplied.is_absolute() or supplied.is_symlink():
            raise ValueError("UnsafeStageRoot")
        root = supplied.resolve(strict=True)
        if root != supplied or not root.is_dir():
            raise ValueError("UnsafeStageRoot")
        manifest_path = root / MANIFEST_NAME
        manifest_stat = manifest_path.lstat()
        if stat.S_ISLNK(manifest_stat.st_mode) or not stat.S_ISREG(manifest_stat.st_mode):
            raise ValueError("UnsafeStageManifest")
        if manifest_stat.st_size > MAX_MANIFEST_BYTES:
            raise ValueError("StageManifestTooLarge")
        manifest_digest, _, manifest_bytes, manifest_identity = _read_regular(
            manifest_path, manifest_stat, capture=True
        )
        manifest = json.loads((manifest_bytes or b"").decode("utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("StageManifestInvalid")
        if (
            manifest.get("state") != "validated"
            or manifest.get("promotion_performed") is not False
            or manifest.get("services_modified") is not False
        ):
            raise ValueError("StageNotPristine")
        if Path(str(manifest.get("stage_root") or "")).resolve() != root:
            raise ValueError("StageManifestRootMismatch")
        entries: list[dict[str, Any]] = []
        totals = {"entries": 0, "bytes": 0}
        identities: dict[Path, tuple[int, int, int, int, int]] = {}
        _scan_directory(root, root, entries, totals, identities)
        if _identity(manifest_path.lstat()) != manifest_identity:
            raise ValueError("StageChangedDuringWitness")
        for path, identity in identities.items():
            if _identity(path.lstat()) != identity:
                raise ValueError("StageChangedDuringWitness")
        tree = {"schema": STAGE_WITNESS_SCHEMA, "entries": entries}
        result.update(
            {
                "status": "WITNESSED",
                "reason": "ValidatedStageWitnessed",
                "stage_tree_sha256": semantic_sha256(tree),
                "manifest_sha256": manifest_digest,
                "entry_count": totals["entries"],
                "total_bytes": totals["bytes"],
                "manifest": manifest,
            }
        )
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError) as error:
        result["reason"] = (
            str(error) if isinstance(error, ValueError) and str(error) else "StageWitnessUnavailable"
        )
    return result


__all__ = ["STAGE_WITNESS_SCHEMA", "witness_validated_stage"]
