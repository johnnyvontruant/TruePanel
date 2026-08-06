"""
Guarded cleanup of completed TruePanel upgrade assets.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .backup_receipt import (
    BACKUP_PREFIX,
    BACKUP_RECEIPT_NAME,
    validate_backup_receipt,
)
from .promotion import MANIFEST_NAME

CLEANUP_CONFIRMATION = "CLEAN_TRUEPANEL"

STAGE_PREFIX = ".truepanel-stage-"

COMPLETED_STATES = {
    "promoted",
    "rolled_back",
}

BACKUP_GENERATIONS_TO_KEEP = 2


@dataclass(frozen=True)
class CleanupAsset:
    path: Path
    kind: str
    action: str
    reason: str


@dataclass(frozen=True)
class CleanupPlan:
    deploy_root: Path
    assets: tuple[CleanupAsset, ...]


def backup_content_identity(
    backup_root: Path,
) -> str:
    """Hash meaningful synchronized backup file content."""
    digest = hashlib.sha256()

    ignored_directory_names = {
        ".git",
        ".venv",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
    }

    ignored_relative_prefixes = {
        "development/backups",
        "development/firmware",
        "development/logs",
    }

    ignored_file_names = {
        BACKUP_RECEIPT_NAME,
        MANIFEST_NAME,
        "truepanel.yaml",
    }

    files: list[Path] = []

    for item in backup_root.rglob("*"):
        relative_path = item.relative_to(
            backup_root
        )
        relative = relative_path.as_posix()

        if any(
            part in ignored_directory_names
            for part in relative_path.parts
        ):
            continue

        if any(
            relative == prefix
            or relative.startswith(
                f"{prefix}/"
            )
            for prefix in ignored_relative_prefixes
        ):
            continue

        if item.name in ignored_file_names:
            continue

        if item.name.endswith(
            (
                ".pyc",
                ".bak",
            )
        ):
            continue

        if any(
            part.startswith(
                ".before-"
            )
            for part in relative_path.parts
        ):
            continue

        if item.name.startswith(
            "truepanel.backup-"
        ):
            continue

        if item.is_file() or item.is_symlink():
            files.append(item)

    for item in sorted(
        files,
        key=lambda candidate: (
            candidate.relative_to(
                backup_root
            ).as_posix()
        ),
    ):
        relative = item.relative_to(
            backup_root
        ).as_posix()

        digest.update(
            relative.encode(
                "utf-8"
            )
        )
        digest.update(b"\\0")

        if item.is_symlink():
            digest.update(b"symlink\\0")
            digest.update(
                os.readlink(
                    item
                ).encode(
                    "utf-8"
                )
            )
            digest.update(b"\\0")
            continue

        digest.update(b"file\\0")

        with item.open("rb") as handle:
            while chunk := handle.read(
                1024 * 1024
            ):
                digest.update(chunk)

        digest.update(b"\\0")

    return digest.hexdigest()

def read_manifest(
    path: Path,
) -> dict[str, Any]:
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
        raise ValueError(
            f"Invalid manifest: {error}"
        ) from error

    if not isinstance(
        payload,
        dict,
    ):
        raise ValueError(
            "Manifest must be an object"
        )

    return payload


def discover_candidates(
    deploy_root: Path,
) -> tuple[
    list[Path],
    list[Path],
]:
    parent = deploy_root.parent

    stages = sorted(
        (
            path.resolve()
            for path in parent.iterdir()
            if (
                path.is_dir()
                and path.name.startswith(
                    STAGE_PREFIX
                )
            )
        ),
        key=lambda path: (
            path.stat().st_mtime
        ),
    )

    backups = sorted(
        (
            path.resolve()
            for path in parent.iterdir()
            if (
                path.is_dir()
                and path.name.startswith(
                    BACKUP_PREFIX
                )
            )
        ),
        key=lambda path: (
            path.stat().st_mtime
        ),
    )

    return stages, backups


def build_cleanup_plan(
    *,
    deploy_root: Path,
) -> CleanupPlan:
    deploy_root = deploy_root.resolve()

    if not deploy_root.is_dir():
        raise ValueError(
            f"Deployment does not exist: "
            f"{deploy_root}"
        )

    stages, backups = discover_candidates(
        deploy_root
    )

    completed_stages: list[
        tuple[Path, dict[str, Any]]
    ] = []

    assets: list[CleanupAsset] = []

    for stage in stages:
        manifest_path = (
            stage / MANIFEST_NAME
        )

        if not manifest_path.is_file():
            assets.append(
                CleanupAsset(
                    path=stage,
                    kind="stage",
                    action="refuse",
                    reason="missing manifest",
                )
            )
            continue

        try:
            manifest = read_manifest(
                manifest_path
            )
        except ValueError as error:
            assets.append(
                CleanupAsset(
                    path=stage,
                    kind="stage",
                    action="refuse",
                    reason=str(error),
                )
            )
            continue

        manifest_stage = Path(
            str(
                manifest.get(
                    "stage_root",
                    "",
                )
            )
        ).resolve()

        manifest_deploy = Path(
            str(
                manifest.get(
                    "deploy_root",
                    "",
                )
            )
        ).resolve()

        if manifest_stage != stage:
            assets.append(
                CleanupAsset(
                    path=stage,
                    kind="stage",
                    action="refuse",
                    reason=(
                        "manifest stage path "
                        "does not match"
                    ),
                )
            )
            continue

        if manifest_deploy != deploy_root:
            assets.append(
                CleanupAsset(
                    path=stage,
                    kind="stage",
                    action="refuse",
                    reason=(
                        "manifest deployment "
                        "does not match"
                    ),
                )
            )
            continue

        state = manifest.get(
            "state"
        )

        if state not in COMPLETED_STATES:
            assets.append(
                CleanupAsset(
                    path=stage,
                    kind="stage",
                    action="keep",
                    reason=(
                        f"incomplete state: "
                        f"{state}"
                    ),
                )
            )
            continue

        completed_stages.append(
            (
                stage,
                manifest,
            )
        )

    verified_backups: dict[
        Path,
        Path,
    ] = {}

    for stage, manifest in (
        completed_stages
    ):
        backup_value = manifest.get(
            "backup_root"
        )

        if not backup_value:
            assets.append(
                CleanupAsset(
                    path=stage,
                    kind="stage",
                    action="refuse",
                    reason=(
                        "completed manifest "
                        "has no backup path"
                    ),
                )
            )
            continue

        backup = Path(
            str(backup_value)
        ).resolve()

        if (
            backup.parent
            != deploy_root.parent
        ):
            assets.append(
                CleanupAsset(
                    path=stage,
                    kind="stage",
                    action="refuse",
                    reason=(
                        "backup is outside "
                        "deployment parent"
                    ),
                )
            )
            continue

        if not backup.name.startswith(
            BACKUP_PREFIX
        ):
            assets.append(
                CleanupAsset(
                    path=stage,
                    kind="stage",
                    action="refuse",
                    reason=(
                        "backup name is unsafe"
                    ),
                )
            )
            continue

        if not backup.is_dir():
            assets.append(
                CleanupAsset(
                    path=stage,
                    kind="stage",
                    action="refuse",
                    reason=(
                        "referenced backup "
                        "is missing"
                    ),
                )
            )
            continue

        verified_backups[backup] = stage

    receipt_errors: dict[
        Path,
        str,
    ] = {}

    for backup in backups:
        if backup in verified_backups:
            continue

        try:
            validate_backup_receipt(
                backup_root=backup,
                deploy_root=deploy_root,
            )
        except ValueError as error:
            receipt_errors[backup] = str(
                error
            )
        else:
            verified_backups[backup] = None

    generation_groups: dict[
        str,
        list[Path],
    ] = {}

    for backup in verified_backups:
        identity = backup_content_identity(
            backup
        )

        generation_groups.setdefault(
            identity,
            [],
        ).append(backup)

    ordered_generations = sorted(
        generation_groups.values(),
        key=lambda group: max(
            path.stat().st_mtime
            for path in group
        ),
        reverse=True,
    )

    retained_backups: set[Path] = set()
    duplicate_backups: set[Path] = set()
    expired_backups: set[Path] = set()

    for index, group in enumerate(
        ordered_generations
    ):
        ordered_group = sorted(
            group,
            key=lambda path: (
                path.stat().st_mtime
            ),
            reverse=True,
        )

        if (
            index
            < BACKUP_GENERATIONS_TO_KEEP
        ):
            retained_backups.add(
                ordered_group[0]
            )
            duplicate_backups.update(
                ordered_group[1:]
            )
        else:
            expired_backups.update(
                ordered_group
            )

    handled_stages: set[Path] = {
        asset.path
        for asset in assets
        if asset.kind == "stage"
    }

    for stage, manifest in (
        completed_stages
    ):
        if stage in handled_stages:
            continue

        backup = Path(
            str(
                manifest["backup_root"]
            )
        ).resolve()

        if (
            backup
            not in verified_backups
        ):
            continue

        assets.append(
            CleanupAsset(
                path=stage,
                kind="stage",
                action="remove",
                reason=(
                    "completed upgrade stage"
                ),
            )
        )

    for backup in backups:
        if backup in retained_backups:
            assets.append(
                CleanupAsset(
                    path=backup,
                    kind="backup",
                    action="keep",
                    reason=(
                        "retained backup generation"
                    ),
                )
            )
        elif backup in duplicate_backups:
            assets.append(
                CleanupAsset(
                    path=backup,
                    kind="backup",
                    action="remove",
                    reason=(
                        "duplicate backup generation"
                    ),
                )
            )
        elif backup in expired_backups:
            assets.append(
                CleanupAsset(
                    path=backup,
                    kind="backup",
                    action="remove",
                    reason=(
                        "generation exceeds "
                        "retention limit"
                    ),
                )
            )
        elif backup in verified_backups:
            assets.append(
                CleanupAsset(
                    path=backup,
                    kind="backup",
                    action="remove",
                    reason=(
                        "verified backup not retained"
                    ),
                )
            )
        else:
            assets.append(
                CleanupAsset(
                    path=backup,
                    kind="backup",
                    action="refuse",
                    reason=receipt_errors.get(
                        backup,
                        (
                            "not referenced by a "
                            "completed manifest"
                        ),
                    ),
                )
            )

    assets.sort(
        key=lambda asset: (
            asset.kind,
            asset.path.name,
        )
    )

    return CleanupPlan(
        deploy_root=deploy_root,
        assets=tuple(assets),
    )


def print_cleanup_plan(
    plan: CleanupPlan,
) -> None:
    print()
    print("TruePanel Upgrade Cleanup")
    print("=========================")
    print()
    print(
        f"Deployment: {plan.deploy_root}"
    )
    print()

    if not plan.assets:
        print(
            "No upgrade assets found."
        )
        return

    for asset in plan.assets:
        print(
            f"{asset.action.upper():7} "
            f"{asset.kind:6} "
            f"{asset.path}"
        )
        print(
            f"        {asset.reason}"
        )


def safe_remove(
    asset: CleanupAsset,
    *,
    deploy_root: Path,
) -> None:
    path = asset.path.resolve()
    parent = deploy_root.parent.resolve()

    if path.parent != parent:
        raise ValueError(
            f"Unsafe cleanup path: {path}"
        )

    expected_prefix = (
        STAGE_PREFIX
        if asset.kind == "stage"
        else BACKUP_PREFIX
    )

    if not path.name.startswith(
        expected_prefix
    ):
        raise ValueError(
            f"Unsafe cleanup name: {path}"
        )

    if path == deploy_root:
        raise ValueError(
            "Refusing to remove deployment"
        )

    shutil.rmtree(path)


def run_cleanup(
    *,
    deploy_root: Path,
    confirmation: str | None = None,
) -> int:
    try:
        plan = build_cleanup_plan(
            deploy_root=deploy_root,
        )
    except ValueError as error:
        print(
            f"Cleanup plan rejected: {error}"
        )
        return 1

    print_cleanup_plan(plan)

    removable = tuple(
        asset
        for asset in plan.assets
        if asset.action == "remove"
    )

    refused = tuple(
        asset
        for asset in plan.assets
        if asset.action == "refuse"
    )

    if confirmation is None:
        print()
        print(
            "DRY RUN: no files were removed."
        )
        print(
            "To apply this plan, use:"
        )
        print(
            f"  --confirm "
            f"{CLEANUP_CONFIRMATION}"
        )
        return (
            1
            if refused
            else 0
        )

    if (
        confirmation
        != CLEANUP_CONFIRMATION
    ):
        print()
        print(
            "Cleanup confirmation rejected."
        )
        print(
            "Required confirmation: "
            f"{CLEANUP_CONFIRMATION}"
        )
        return 2

    if refused:
        print()
        print(
            "Cleanup refused because unsafe "
            "assets were discovered."
        )
        return 1

    for asset in removable:
        try:
            safe_remove(
                asset,
                deploy_root=(
                    plan.deploy_root
                ),
            )
        except (
            OSError,
            ValueError,
        ) as error:
            print(
                f"FAIL remove {asset.path}: "
                f"{error}"
            )
            return 1

        print(
            f"REMOVED {asset.path}"
        )

    print()
    print(
        "Cleanup completed without "
        "touching services."
    )
    return 0
