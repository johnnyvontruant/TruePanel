"""
Guarded TruePanel upgrade promotion and rollback.

Promotion operates on an already validated staging tree. The caller supplies
service restart and verification functions, allowing the complete lifecycle
to be tested without touching the live host.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .backup_receipt import (
    BACKUP_PREFIX,
    BACKUP_RECEIPT_NAME,
    write_backup_receipt,
)
from .checks import (
    RSYNC_EXCLUDES,
    command_detail,
    timestamp_token,
)

MANIFEST_NAME = (
    "truepanel-upgrade-manifest.json"
)

PROMOTION_EXCLUDES = (
    *RSYNC_EXCLUDES,
    MANIFEST_NAME,
    BACKUP_RECEIPT_NAME,
)

PROMOTION_DEPLOY_EXCLUDES = (
    "bin/",
)


@dataclass(frozen=True)
class PromotionPlan:
    stage_root: Path
    deploy_root: Path
    backup_root: Path
    manifest_path: Path


def run_command(
    command: list[str],
    *,
    timeout: float = 120.0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def load_manifest(
    stage_root: Path,
) -> dict[str, Any]:
    manifest_path = (
        stage_root / MANIFEST_NAME
    )

    if not manifest_path.is_file():
        raise ValueError(
            f"Missing upgrade manifest: {manifest_path}"
        )

    try:
        manifest = json.loads(
            manifest_path.read_text(
                encoding="utf-8"
            )
        )
    except (
        json.JSONDecodeError,
        OSError,
    ) as error:
        raise ValueError(
            f"Invalid upgrade manifest: {error}"
        ) from error

    if not isinstance(
        manifest,
        dict,
    ):
        raise ValueError(
            "Upgrade manifest must be an object"
        )

    return manifest


def write_manifest(
    path: Path,
    manifest: dict[str, Any],
) -> None:
    temporary = path.with_suffix(
        path.suffix + ".tmp"
    )

    temporary.write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    temporary.replace(path)


def default_backup_root(
    deploy_root: Path,
) -> Path:
    return (
        deploy_root.parent
        / (
            ".truepanel-backup-"
            + timestamp_token()
        )
    )


def build_promotion_plan(
    *,
    stage_root: Path,
    deploy_root: Path,
    backup_root: Path | None = None,
) -> PromotionPlan:
    stage_root = stage_root.resolve()
    deploy_root = deploy_root.resolve()

    if not stage_root.is_dir():
        raise ValueError(
            f"Stage does not exist: {stage_root}"
        )

    if not deploy_root.is_dir():
        raise ValueError(
            f"Deployment does not exist: {deploy_root}"
        )

    manifest = load_manifest(
        stage_root
    )

    if (
        manifest.get("state")
        != "validated"
    ):
        raise ValueError(
            "Stage is not in validated state"
        )

    manifest_stage = Path(
        str(
            manifest.get(
                "stage_root",
                "",
            )
        )
    ).resolve()

    manifest_deployment = Path(
        str(
            manifest.get(
                "deploy_root",
                "",
            )
        )
    ).resolve()

    if manifest_stage != stage_root:
        raise ValueError(
            "Manifest stage root does not match"
        )

    if (
        manifest_deployment
        != deploy_root
    ):
        raise ValueError(
            "Manifest deployment root does not match"
        )

    selected_backup = (
        backup_root.resolve()
        if backup_root is not None
        else default_backup_root(
            deploy_root
        )
    )

    if (
        selected_backup.parent
        != deploy_root.parent
    ):
        raise ValueError(
            "Backup must be a sibling of "
            "the deployment"
        )

    if not selected_backup.name.startswith(
        BACKUP_PREFIX
    ):
        raise ValueError(
            "Backup name is unsafe"
        )

    if selected_backup in (
        stage_root,
        deploy_root,
    ):
        raise ValueError(
            "Backup root must be distinct"
        )

    if selected_backup.exists():
        raise ValueError(
            f"Backup already exists: {selected_backup}"
        )

    return PromotionPlan(
        stage_root=stage_root,
        deploy_root=deploy_root,
        backup_root=selected_backup,
        manifest_path=(
            stage_root / MANIFEST_NAME
        ),
    )


def sync_command(
    source: Path,
    destination: Path,
    *,
    extra_excludes: tuple[str, ...] = (),
) -> list[str]:
    command = [
        "rsync",
        "-a",
        "--delete",
    ]

    for exclusion in (
        *PROMOTION_EXCLUDES,
        *extra_excludes,
    ):
        command.append(
            f"--exclude={exclusion}"
        )

    command.extend(
        [
            str(source) + "/",
            str(destination) + "/",
        ]
    )

    return command


def sync_tree(
    source: Path,
    destination: Path,
    *,
    runner: Callable[..., Any],
    extra_excludes: tuple[str, ...] = (),
) -> tuple[bool, str]:
    destination.mkdir(
        parents=True,
        exist_ok=True,
    )

    response = runner(
        sync_command(
            source,
            destination,
            extra_excludes=extra_excludes,
        ),
        timeout=120.0,
    )

    if response.returncode != 0:
        return (
            False,
            command_detail(
                response
            ),
        )

    return (
        True,
        str(destination),
    )


def update_manifest_state(
    plan: PromotionPlan,
    *,
    state: str,
    promotion_performed: bool,
    services_modified: bool,
    verification_result: int,
    rollback_performed: bool,
) -> None:
    manifest = load_manifest(
        plan.stage_root
    )

    manifest.update(
        {
            "state": state,
            "backup_root": str(
                plan.backup_root
            ),
            "promotion_performed": (
                promotion_performed
            ),
            "services_modified": (
                services_modified
            ),
            "verification_result": (
                verification_result
            ),
            "rollback_performed": (
                rollback_performed
            ),
        }
    )

    write_manifest(
        plan.manifest_path,
        manifest,
    )


def promote_with_rollback(
    plan: PromotionPlan,
    *,
    runner: Callable[..., Any] = run_command,
    restarter: Callable[[Path], int],
    verifier: Callable[[Path], int],
) -> int:
    backup_ok, backup_detail = sync_tree(
        plan.deploy_root,
        plan.backup_root,
        runner=runner,
    )

    if not backup_ok:
        print(
            f"FAIL  Backup creation: "
            f"{backup_detail}"
        )
        return 1

    try:
        write_backup_receipt(
            backup_root=plan.backup_root,
            deploy_root=plan.deploy_root,
            source_root=plan.deploy_root,
            kind="promotion",
        )
    except (
        OSError,
        ValueError,
    ) as error:
        print(
            "FAIL  Backup receipt: "
            f"{error}"
        )
        return 1

    promotion_ok, promotion_detail = (
        sync_tree(
            plan.stage_root,
            plan.deploy_root,
            runner=runner,
            extra_excludes=(
                PROMOTION_DEPLOY_EXCLUDES
            ),
        )
    )

    if not promotion_ok:
        print(
            f"FAIL  Promotion: "
            f"{promotion_detail}"
        )

        shutil.rmtree(
            plan.backup_root,
            ignore_errors=True,
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
        update_manifest_state(
            plan,
            state="promoted",
            promotion_performed=True,
            services_modified=True,
            verification_result=0,
            rollback_performed=False,
        )

        print(
            "PROMOTION VERIFIED"
        )
        print(
            f"Backup retained: "
            f"{plan.backup_root}"
        )
        return 0

    print(
        "Verification failed; "
        "starting automatic rollback."
    )

    rollback_ok, rollback_detail = (
        sync_tree(
            plan.backup_root,
            plan.deploy_root,
            runner=runner,
        )
    )

    if not rollback_ok:
        update_manifest_state(
            plan,
            state="rollback_failed",
            promotion_performed=True,
            services_modified=True,
            verification_result=(
                verification_result
            ),
            rollback_performed=False,
        )

        print(
            f"FAIL  Rollback: "
            f"{rollback_detail}"
        )
        return 2

    rollback_restart = restarter(
        plan.deploy_root
    )

    if rollback_restart == 0:
        rollback_verify = verifier(
            plan.deploy_root
        )
    else:
        rollback_verify = (
            rollback_restart
        )

    if rollback_verify != 0:
        update_manifest_state(
            plan,
            state="rollback_failed",
            promotion_performed=True,
            services_modified=True,
            verification_result=(
                verification_result
            ),
            rollback_performed=True,
        )

        print(
            "FAIL  Rollback verification failed"
        )
        return 2

    update_manifest_state(
        plan,
        state="rolled_back",
        promotion_performed=True,
        services_modified=True,
        verification_result=(
            verification_result
        ),
        rollback_performed=True,
    )

    print(
        "ROLLBACK VERIFIED"
    )
    return 1


PROMOTION_CONFIRMATION = "PROMOTE_TRUEPANEL"


def restart_truepanel(
    deploy_root: Path,
    *,
    runner: Callable[..., Any] = run_command,
) -> int:
    startup = (
        deploy_root
        / "start-truepanel.sh"
    )

    if not startup.is_file():
        print(
            f"Missing startup script: {startup}"
        )
        return 1

    response = runner(
        [
            str(startup),
        ],
        timeout=180.0,
    )

    if response.returncode != 0:
        print(
            "Service restart failed: "
            + command_detail(response)
        )

    return int(
        response.returncode
    )


def verify_truepanel(
    deploy_root: Path,
    *,
    runner: Callable[..., Any] = run_command,
    sleeper: Callable[[float], None] = time.sleep,
    attempts: int = 8,
    retry_delay: float = 1.0,
) -> int:
    """
    Verify with the deployed generation's own Python/runtime.

    Service startup can briefly race Mission Control or LCD readiness, so
    retry only when every reported failure is one of those transient checks.
    """

    deploy_root = deploy_root.resolve()

    python_path = (
        deploy_root
        / ".venv"
        / "bin"
        / "python"
    )
    launcher = (
        deploy_root
        / "truepanel.py"
    )

    if not python_path.is_file():
        print(
            "Missing deployed Python runtime: "
            f"{python_path}"
        )
        return 1

    if not launcher.is_file():
        print(
            "Missing deployed launcher: "
            f"{launcher}"
        )
        return 1

    if attempts < 1:
        raise ValueError(
            "Verification attempts must be positive"
        )

    command = [
        str(python_path),
        str(launcher),
        "verify",
        "--root",
        str(deploy_root),
    ]

    for attempt in range(
        1,
        attempts + 1,
    ):
        response = runner(
            command,
            timeout=120.0,
        )

        stdout = str(
            getattr(
                response,
                "stdout",
                "",
            )
            or ""
        )
        stderr = str(
            getattr(
                response,
                "stderr",
                "",
            )
            or ""
        )

        if stdout:
            print(
                stdout.rstrip()
            )

        if response.returncode == 0:
            return 0

        failure_lines = [
            line
            for line in stdout.splitlines()
            if line.startswith("FAIL  ")
        ]

        transient_only = bool(
            failure_lines
        ) and all(
            (
                line.startswith(
                    "FAIL  Mission Control API"
                )
                or line.startswith(
                    "FAIL  LCD transport"
                )
            )
            for line in failure_lines
        )

        if (
            not transient_only
            or attempt >= attempts
        ):
            if stderr:
                print(
                    stderr.rstrip()
                )
            return int(
                response.returncode
            )

        print(
            "Deployment verification not ready "
            f"(attempt {attempt}/{attempts}); "
            "retrying."
        )
        sleeper(
            retry_delay
        )

    return 1


def run_promotion(
    *,
    stage_root: Path | None,
    deploy_root: Path,
    backup_root: Path | None = None,
    confirmation: str | None = None,
    runner: Callable[..., Any] = run_command,
    restarter: Callable[[Path], int] | None = None,
    verifier: Callable[[Path], int] | None = None,
) -> int:
    print()
    print("TruePanel Guarded Upgrade Promotion")
    print("==================================")
    print()

    if (
        confirmation
        != PROMOTION_CONFIRMATION
    ):
        print(
            "Promotion confirmation rejected."
        )
        print(
            "Required confirmation: "
            f"{PROMOTION_CONFIRMATION}"
        )
        return 2

    if stage_root is None:
        print(
            "Promotion requires an explicit "
            "--stage-root."
        )
        return 2

    try:
        plan = build_promotion_plan(
            stage_root=stage_root,
            deploy_root=deploy_root,
            backup_root=backup_root,
        )
    except ValueError as error:
        print(
            f"Promotion plan rejected: {error}"
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
        f"Stage:      {plan.stage_root}"
    )
    print(
        f"Deployment: {plan.deploy_root}"
    )
    print(
        f"Backup:     {plan.backup_root}"
    )
    print()

    return promote_with_rollback(
        plan,
        runner=runner,
        restarter=selected_restarter,
        verifier=selected_verifier,
    )
