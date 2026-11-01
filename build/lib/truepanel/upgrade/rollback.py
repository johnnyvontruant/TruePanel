"""
Guarded TruePanel operator rollback.

Rollback restores application files from an explicitly selected retained
backup while preserving runtime configuration and the deployed virtual
environment. Before restoring, it creates a fresh safety backup of the
current installation.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .backup_receipt import (
    BACKUP_PREFIX,
    validate_backup_receipt,
    write_backup_receipt,
)
from .promotion import (
    restart_truepanel,
    run_command,
    sync_tree,
    timestamp_token,
    verify_truepanel,
)

ROLLBACK_CONFIRMATION = (
    "ROLLBACK_TRUEPANEL"
)

ROLLBACK_BACKUP_PREFIX = (
    ".truepanel-backup-rollback-"
)

REQUIRED_BACKUP_PATHS = (
    "truepanel.py",
    "truepanel",
    "qnaplcd",
    "start-truepanel.sh",
    "deploy-truenas.sh",
    "pyproject.toml",
)


@dataclass(frozen=True)
class RollbackPlan:
    deploy_root: Path
    selected_backup_root: Path
    safety_backup_root: Path


def default_safety_backup_root(
    deploy_root: Path,
) -> Path:
    return (
        deploy_root.parent
        / (
            ROLLBACK_BACKUP_PREFIX
            + timestamp_token()
        )
    )


def validate_backup_contents(
    backup_root: Path,
) -> list[str]:
    return [
        f"Missing backup path: "
        f"{backup_root / relative}"
        for relative in REQUIRED_BACKUP_PATHS
        if not (
            backup_root / relative
        ).exists()
    ]


def build_rollback_plan(
    *,
    deploy_root: Path,
    selected_backup_root: Path,
    safety_backup_root: (
        Path | None
    ) = None,
) -> RollbackPlan:
    deploy_root = deploy_root.resolve()
    selected_backup_root = (
        selected_backup_root.resolve()
    )

    if not deploy_root.is_dir():
        raise ValueError(
            f"Deployment does not exist: "
            f"{deploy_root}"
        )

    if not selected_backup_root.is_dir():
        raise ValueError(
            f"Selected backup does not exist: "
            f"{selected_backup_root}"
        )

    parent = deploy_root.parent.resolve()

    if (
        selected_backup_root.parent
        != parent
    ):
        raise ValueError(
            "Selected backup must be a sibling "
            "of the deployment"
        )

    if not (
        selected_backup_root.name.startswith(
            BACKUP_PREFIX
        )
    ):
        raise ValueError(
            "Selected backup name is unsafe"
        )

    if selected_backup_root == deploy_root:
        raise ValueError(
            "Selected backup cannot be the "
            "deployment"
        )

    errors = validate_backup_contents(
        selected_backup_root
    )

    if errors:
        raise ValueError(
            "; ".join(errors)
        )

    try:
        validate_backup_receipt(
            backup_root=(
                selected_backup_root
            ),
            deploy_root=deploy_root,
        )
    except ValueError as error:
        raise ValueError(
            f"Selected backup receipt "
            f"rejected: {error}"
        ) from error

    selected_safety_backup = (
        safety_backup_root.resolve()
        if safety_backup_root is not None
        else default_safety_backup_root(
            deploy_root
        )
    )

    if (
        selected_safety_backup.parent
        != parent
    ):
        raise ValueError(
            "Safety backup must be a sibling "
            "of the deployment"
        )

    if not (
        selected_safety_backup.name.startswith(
            ROLLBACK_BACKUP_PREFIX
        )
    ):
        raise ValueError(
            "Safety backup name is unsafe"
        )

    if selected_safety_backup in (
        deploy_root,
        selected_backup_root,
    ):
        raise ValueError(
            "Safety backup path must be distinct"
        )

    if selected_safety_backup.exists():
        raise ValueError(
            f"Safety backup already exists: "
            f"{selected_safety_backup}"
        )

    return RollbackPlan(
        deploy_root=deploy_root,
        selected_backup_root=(
            selected_backup_root
        ),
        safety_backup_root=(
            selected_safety_backup
        ),
    )


def rollback_with_recovery(
    plan: RollbackPlan,
    *,
    runner: Callable[..., Any] = (
        run_command
    ),
    restarter: Callable[
        [Path],
        int,
    ],
    verifier: Callable[
        [Path],
        int,
    ],
) -> int:
    safety_ok, safety_detail = sync_tree(
        plan.deploy_root,
        plan.safety_backup_root,
        runner=runner,
    )

    if not safety_ok:
        print(
            "FAIL  Pre-rollback safety backup: "
            f"{safety_detail}"
        )
        return 1

    try:
        write_backup_receipt(
            backup_root=(
                plan.safety_backup_root
            ),
            deploy_root=plan.deploy_root,
            source_root=plan.deploy_root,
            kind="rollback_safety",
        )
    except (
        OSError,
        ValueError,
    ) as error:
        print(
            "FAIL  Safety backup receipt: "
            f"{error}"
        )
        return 1

    restore_ok, restore_detail = sync_tree(
        plan.selected_backup_root,
        plan.deploy_root,
        runner=runner,
    )

    if not restore_ok:
        print(
            f"FAIL  Selected backup restore: "
            f"{restore_detail}"
        )
        print(
            "Restore may be partial; "
            "recovering the pre-rollback state."
        )

        recovery_ok, recovery_detail = (
            sync_tree(
                plan.safety_backup_root,
                plan.deploy_root,
                runner=runner,
            )
        )

        if not recovery_ok:
            print(
                "FAIL  Pre-rollback recovery: "
                f"{recovery_detail}"
            )
            return 2

        recovery_restart = restarter(
            plan.deploy_root
        )

        if recovery_restart == 0:
            recovery_verify = verifier(
                plan.deploy_root
            )
        else:
            recovery_verify = (
                recovery_restart
            )

        if recovery_verify != 0:
            print(
                "FAIL  Pre-rollback state "
                "verification failed"
            )
            return 2

        print(
            "PRE-ROLLBACK STATE RESTORED"
        )
        return 1

    restart_result = restarter(
        plan.deploy_root
    )

    if restart_result == 0:
        verification_result = verifier(
            plan.deploy_root
        )
    else:
        verification_result = (
            restart_result
        )

    if verification_result == 0:
        print("ROLLBACK VERIFIED")
        print(
            "Pre-rollback safety backup retained: "
            f"{plan.safety_backup_root}"
        )
        return 0

    print(
        "Rollback verification failed; "
        "restoring the pre-rollback state."
    )

    recovery_ok, recovery_detail = (
        sync_tree(
            plan.safety_backup_root,
            plan.deploy_root,
            runner=runner,
        )
    )

    if not recovery_ok:
        print(
            "FAIL  Pre-rollback recovery: "
            f"{recovery_detail}"
        )
        return 2

    recovery_restart = restarter(
        plan.deploy_root
    )

    if recovery_restart == 0:
        recovery_verify = verifier(
            plan.deploy_root
        )
    else:
        recovery_verify = (
            recovery_restart
        )

    if recovery_verify != 0:
        print(
            "FAIL  Pre-rollback state "
            "verification failed"
        )
        return 2

    print(
        "PRE-ROLLBACK STATE RESTORED"
    )
    return 1


def run_rollback(
    *,
    deploy_root: Path,
    selected_backup_root: (
        Path | None
    ),
    safety_backup_root: (
        Path | None
    ) = None,
    confirmation: str | None = None,
    runner: Callable[..., Any] = (
        run_command
    ),
    restarter: Callable[
        [Path],
        int,
    ] | None = None,
    verifier: Callable[
        [Path],
        int,
    ] | None = None,
) -> int:
    print()
    print("TruePanel Guarded Rollback")
    print("==========================")
    print()

    if (
        confirmation
        != ROLLBACK_CONFIRMATION
    ):
        print(
            "Rollback confirmation rejected."
        )
        print(
            "Required confirmation: "
            f"{ROLLBACK_CONFIRMATION}"
        )
        return 2

    if selected_backup_root is None:
        print(
            "Rollback requires an explicit "
            "--backup-root."
        )
        return 2

    try:
        plan = build_rollback_plan(
            deploy_root=deploy_root,
            selected_backup_root=(
                selected_backup_root
            ),
            safety_backup_root=(
                safety_backup_root
            ),
        )
    except ValueError as error:
        print(
            f"Rollback plan rejected: {error}"
        )
        return 1

    selected_restarter = (
        restarter
        if restarter is not None
        else lambda root: restart_truepanel(
            root,
            runner=runner,
        )
    )

    selected_verifier = (
        verifier
        if verifier is not None
        else verify_truepanel
    )

    print(
        f"Deployment:    "
        f"{plan.deploy_root}"
    )
    print(
        f"Restore from:  "
        f"{plan.selected_backup_root}"
    )
    print(
        f"Safety backup: "
        f"{plan.safety_backup_root}"
    )
    print()

    return rollback_with_recovery(
        plan,
        runner=runner,
        restarter=selected_restarter,
        verifier=selected_verifier,
    )
