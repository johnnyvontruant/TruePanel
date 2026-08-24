"""
TruePanel staged upgrade preparation.

This module validates and stages an upgrade without modifying the deployed
installation or controlling services.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from truepanel.paths import installation_root

STAGE_PREFIX = ".truepanel-stage-"

RSYNC_EXCLUDES = (
    ".git",
    ".venv/",
    ".pytest_cache/",
    ".ruff_cache/",
    "__pycache__/",
    "*.pyc",
    "*.bak",
    "*.before-*",
    "truepanel.backup-*",
    "development/logs/",
    "development/backups/",
    "development/firmware/",
    "truepanel.yaml",
)


@dataclass(frozen=True)
class UpgradePlan:
    source_root: str
    deploy_root: str
    stage_root: str
    source_version: str
    deployed_version: str
    python_path: str
    exclusions: tuple[str, ...]


def run_command(
    command: list[str],
    *,
    timeout: float = 60.0,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def command_detail(
    response: Any,
) -> str:
    return (
        str(
            getattr(
                response,
                "stderr",
                "",
            )
        ).strip()
        or str(
            getattr(
                response,
                "stdout",
                "",
            )
        ).strip()
        or (
            "exit code "
            f"{getattr(response, 'returncode', 'unknown')}"
        )
    )


def read_version(
    root: Path,
) -> str:
    path = (
        root
        / "truepanel"
        / "__init__.py"
    )

    if not path.is_file():
        raise ValueError(
            f"Missing package version file: {path}"
        )

    namespace: dict[str, Any] = {}
    exec(
        compile(
            path.read_text(
                encoding="utf-8"
            ),
            str(path),
            "exec",
        ),
        namespace,
    )

    version = namespace.get(
        "__version__"
    )

    if not isinstance(
        version,
        str,
    ) or not version.strip():
        raise ValueError(
            f"Invalid package version in {path}"
        )

    return version.strip()


def select_python(
    deploy_root: Path,
) -> Path:
    deployed_python = (
        deploy_root
        / ".venv"
        / "bin"
        / "python"
    )

    if deployed_python.is_file():
        return deployed_python

    fallback = Path(
        sys.executable
    )

    if not fallback.is_file():
        raise ValueError(
            "Python is unavailable"
        )

    return fallback


def validate_source(
    source_root: Path,
) -> list[str]:
    required = (
        source_root / "truepanel.py",
        source_root / "truepanel",
        source_root / "start-truepanel.sh",
        source_root / "deploy-truenas.sh",
        source_root / "pyproject.toml",
    )

    return [
        f"Missing source path: {path}"
        for path in required
        if not path.exists()
    ]


def validate_deployment(
    deploy_root: Path,
) -> list[str]:
    required = (
        deploy_root,
        deploy_root / "truepanel.py",
        deploy_root / "truepanel",
        deploy_root / "truepanel.yaml",
    )

    return [
        f"Missing deployed path: {path}"
        for path in required
        if not path.exists()
    ]


def timestamp_token() -> str:
    return datetime.now(
        UTC
    ).strftime(
        "%Y%m%dT%H%M%SZ"
    )


def default_stage_root(
    deploy_root: Path,
) -> Path:
    return (
        deploy_root.parent
        / (
            STAGE_PREFIX
            + timestamp_token()
        )
    )


def build_plan(
    *,
    source_root: Path,
    deploy_root: Path,
    stage_root: Path | None = None,
) -> UpgradePlan:
    source_root = (
        source_root.resolve()
    )
    deploy_root = (
        deploy_root.resolve()
    )

    if source_root == deploy_root:
        raise ValueError(
            "Source and deployment roots must differ"
        )

    source_errors = validate_source(
        source_root
    )
    deployment_errors = (
        validate_deployment(
            deploy_root
        )
    )
    errors = (
        source_errors
        + deployment_errors
    )

    if errors:
        raise ValueError(
            "; ".join(errors)
        )

    selected_stage = (
        stage_root.resolve()
        if stage_root is not None
        else default_stage_root(
            deploy_root
        )
    )

    if selected_stage in (
        source_root,
        deploy_root,
    ):
        raise ValueError(
            "Stage root must differ from source and deployment"
        )

    return UpgradePlan(
        source_root=str(
            source_root
        ),
        deploy_root=str(
            deploy_root
        ),
        stage_root=str(
            selected_stage
        ),
        source_version=read_version(
            source_root
        ),
        deployed_version=read_version(
            deploy_root
        ),
        python_path=str(
            select_python(
                deploy_root
            )
        ),
        exclusions=RSYNC_EXCLUDES,
    )


def rsync_command(
    plan: UpgradePlan,
) -> list[str]:
    command = [
        "rsync",
        "-a",
        "--delete",
    ]

    for exclusion in (
        plan.exclusions
    ):
        command.append(
            f"--exclude={exclusion}"
        )

    command.extend(
        [
            (
                plan.source_root
                + "/"
            ),
            (
                plan.stage_root
                + "/"
            ),
        ]
    )

    return command


def print_plan(
    plan: UpgradePlan,
) -> None:
    print(
        f"Source:             "
        f"{plan.source_root}"
    )
    print(
        f"Deployment:         "
        f"{plan.deploy_root}"
    )
    print(
        f"Stage:              "
        f"{plan.stage_root}"
    )
    print(
        f"Source version:     "
        f"{plan.source_version}"
    )
    print(
        f"Deployed version:   "
        f"{plan.deployed_version}"
    )
    print(
        f"Validation Python:  "
        f"{plan.python_path}"
    )
    print()
    print("Preserved or excluded:")

    for exclusion in (
        plan.exclusions
    ):
        print(
            f"  {exclusion}"
        )


def prepare_stage(
    plan: UpgradePlan,
    *,
    runner: Callable[..., Any] = run_command,
) -> tuple[
    bool,
    str,
]:
    stage_root = Path(
        plan.stage_root
    )
    deploy_root = Path(
        plan.deploy_root
    )

    if stage_root.exists():
        return (
            False,
            (
                "Stage already exists: "
                f"{stage_root}"
            ),
        )

    stage_root.mkdir(
        parents=True,
        exist_ok=False,
    )

    response = runner(
        rsync_command(plan),
        timeout=120.0,
    )

    if response.returncode != 0:
        shutil.rmtree(
            stage_root,
            ignore_errors=True,
        )
        return (
            False,
            command_detail(
                response
            ),
        )

    deployed_config = (
        deploy_root
        / "truepanel.yaml"
    )
    staged_config = (
        stage_root
        / "truepanel.yaml"
    )

    shutil.copy2(
        deployed_config,
        staged_config,
    )

    python_path = Path(
        plan.python_path
    )

    compile_response = runner(
        [
            str(python_path),
            "-m",
            "compileall",
            "-q",
            str(
                stage_root
                / "truepanel"
            ),
            str(
                stage_root
                / "qnaplcd"
            ),
            str(
                stage_root
                / "truepanel.py"
            ),
            str(
                stage_root
                / "collector.py"
            ),
            str(
                stage_root
                / "lcd-menu.py"
            ),
            str(
                stage_root
                / "mission_control_web.py"
            ),
        ],
        timeout=120.0,
    )

    if (
        compile_response.returncode
        != 0
    ):
        shutil.rmtree(
            stage_root,
            ignore_errors=True,
        )
        return (
            False,
            (
                "Staged compilation failed: "
                + command_detail(
                    compile_response
                )
            ),
        )

    staged_version = read_version(
        stage_root
    )

    if (
        staged_version
        != plan.source_version
    ):
        shutil.rmtree(
            stage_root,
            ignore_errors=True,
        )
        return (
            False,
            (
                "Staged version mismatch: "
                f"{staged_version} != "
                f"{plan.source_version}"
            ),
        )

    manifest = {
        **asdict(plan),
        "created_at": (
            datetime.now(
                UTC
            ).isoformat()
        ),
        "state": "validated",
        "promotion_performed": False,
        "services_modified": False,
        "configuration_source": str(
            deployed_config
        ),
    }

    (
        stage_root
        / "truepanel-upgrade-manifest.json"
    ).write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    return (
        True,
        str(stage_root),
    )


def run_upgrade(
    *,
    source_root: Path | None = None,
    deploy_root: Path | None = None,
    stage_root: Path | None = None,
    dry_run: bool = False,
    stage_only: bool = False,
    runner: Callable[..., Any] = run_command,
) -> int:
    source = (
        source_root.resolve()
        if source_root is not None
        else Path.cwd().resolve()
    )
    deployment = installation_root(
        deploy_root
    )

    print("\nTruePanel Upgrade")
    print("=================\n")

    try:
        plan = build_plan(
            source_root=source,
            deploy_root=deployment,
            stage_root=stage_root,
        )
    except ValueError as error:
        print(f"FAIL  {error}")
        return 1

    print_plan(plan)

    if dry_run:
        print("\nUpgrade Result")
        print("--------------")
        print(
            "DRY RUN COMPLETE"
        )
        print(
            "No files or services were changed."
        )
        return 0

    if not stage_only:
        print("\nFAIL  Promotion is not implemented yet.")
        print(
            "Use --dry-run or --stage-only."
        )
        return 2

    ok, detail = prepare_stage(
        plan,
        runner=runner,
    )

    print("\nUpgrade Result")
    print("--------------")

    if not ok:
        print(
            f"FAIL  {detail}"
        )
        return 1

    print(
        f"STAGED AND VALIDATED  {detail}"
    )
    print(
        "The deployed installation and services "
        "were not changed."
    )
    return 0
