"""
Guarded cleanup of completed TruePanel upgrade assets.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .backup_receipt import (
    BACKUP_PREFIX,
    validate_backup_receipt,
)
from .promotion import MANIFEST_NAME

CLEANUP_CONFIRMATION = "CLEAN_TRUEPANEL"

STAGE_PREFIX = ".truepanel-stage-"

COMPLETED_STATES = {
    "promoted",
    "rolled_back",
}


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

    newest_backup = (
        max(
            verified_backups,
            key=lambda path: (
                path.stat().st_mtime
            ),
        )
        if verified_backups
        else None
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
        if backup == newest_backup:
            assets.append(
                CleanupAsset(
                    path=backup,
                    kind="backup",
                    action="keep",
                    reason=(
                        "newest verified backup"
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
                        "older verified backup"
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
