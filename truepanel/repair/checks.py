"""
TruePanel lifecycle repair.

Repairs service units, the Mission Control environment, systemd state,
and TrueNAS POSTINIT restoration without modifying application code,
configuration, history, sockets, or hardware state.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from truepanel.verify import run_verify
from truepanel.verify.checks import (
    environment_root,
    project_root,
    systemd_root,
)

LCD_SERVICE = "truepanel.service"
MISSION_SERVICE = "truepanel-mission-control.service"

POSTINIT_COMMENT = "TruePanel"
POSTINIT_TIMEOUT = 30


def run_command(
    command: list[str],
    *,
    timeout: float = 15.0,
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
        str(getattr(response, "stderr", "")).strip()
        or str(getattr(response, "stdout", "")).strip()
        or f"exit code {getattr(response, 'returncode', 'unknown')}"
    )


def postinit_payload(
    root: Path,
) -> dict[str, Any]:
    return {
        "type": "SCRIPT",
        "command": "",
        "script": str(
            root / "start-truepanel.sh"
        ),
        "when": "POSTINIT",
        "enabled": True,
        "timeout": POSTINIT_TIMEOUT,
        "comment": POSTINIT_COMMENT,
    }


def find_postinit_task(
    tasks: list[dict[str, Any]],
    root: Path,
) -> dict[str, Any] | None:
    expected_script = str(
        root / "start-truepanel.sh"
    )

    for task in tasks:
        if (
            task.get("type") == "SCRIPT"
            and task.get("script")
            == expected_script
        ):
            return task

    for task in tasks:
        if (
            task.get("comment")
            == POSTINIT_COMMENT
        ):
            return task

    return None


def postinit_action(
    tasks: list[dict[str, Any]],
    root: Path,
) -> tuple[
    str,
    int | None,
    dict[str, Any],
]:
    payload = postinit_payload(root)
    task = find_postinit_task(
        tasks,
        root,
    )

    if task is None:
        return (
            "create",
            None,
            payload,
        )

    matches = all(
        task.get(key) == value
        for key, value in payload.items()
    )

    if matches:
        return (
            "none",
            int(task["id"]),
            payload,
        )

    return (
        "update",
        int(task["id"]),
        payload,
    )


def read_postinit_tasks(
    *,
    runner: Callable[..., Any] = run_command,
) -> tuple[
    list[dict[str, Any]] | None,
    str | None,
]:
    try:
        response = runner(
            [
                "midclt",
                "call",
                "initshutdownscript.query",
            ],
            timeout=15.0,
        )
    except (
        OSError,
        subprocess.SubprocessError,
    ) as error:
        return None, str(error)

    if response.returncode != 0:
        return (
            None,
            command_detail(response),
        )

    try:
        payload = json.loads(
            response.stdout
        )
    except (
        TypeError,
        json.JSONDecodeError,
    ) as error:
        return (
            None,
            f"Invalid middleware response: {error}",
        )

    if not isinstance(payload, list):
        return (
            None,
            "Middleware response was not a task list",
        )

    return payload, None


def service_state(
    service: str,
    action: str,
    *,
    runner: Callable[..., Any] = run_command,
) -> tuple[bool, str]:
    try:
        response = runner(
            [
                "systemctl",
                action,
                service,
            ],
            timeout=10.0,
        )
    except (
        OSError,
        subprocess.SubprocessError,
    ) as error:
        return False, str(error)

    detail = (
        response.stdout.strip()
        or response.stderr.strip()
        or "unknown"
    )

    return (
        response.returncode == 0,
        detail,
    )


def files_differ(
    source: Path,
    destination: Path,
) -> bool:
    if not destination.is_file():
        return True

    return (
        source.read_bytes()
        != destination.read_bytes()
    )


def install_file(
    source: Path,
    destination: Path,
) -> None:
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = destination.with_name(
        f".{destination.name}.truepanel-repair"
    )

    shutil.copyfile(
        source,
        temporary,
    )
    temporary.chmod(0o644)
    os.replace(
        temporary,
        destination,
    )


def generate_lifecycle_files(
    root: Path,
    *,
    env_root: Path | None = None,
    runner: Callable[..., Any] = run_command,
) -> tuple[
    tempfile.TemporaryDirectory[str] | None,
    Path | None,
    Path | None,
    str | None,
]:
    startup = root / "start-truepanel.sh"

    if not startup.is_file():
        return (
            None,
            None,
            None,
            f"Missing startup script: {startup}",
        )

    sandbox = tempfile.TemporaryDirectory(
        prefix="truepanel-repair-"
    )
    sandbox_root = Path(sandbox.name)
    generated_systemd = (
        sandbox_root / "systemd"
    )
    generated_environment = (
        sandbox_root / "default"
    )
    installed_environment_root = (
        env_root
        if env_root is not None
        else environment_root()
    )

    environment = os.environ.copy()
    environment.update(
        {
            "TRUEPANEL_SYSTEMD_DIR": str(
                generated_systemd
            ),
            "TRUEPANEL_ENV_DIR": str(
                generated_environment
            ),
            "TRUEPANEL_SKIP_SYSTEMCTL": "true",
        }
    )

    try:
        response = runner(
            [
                "bash",
                str(startup),
            ],
            timeout=20.0,
            env=environment,
        )
    except (
        OSError,
        subprocess.SubprocessError,
    ) as error:
        sandbox.cleanup()
        return (
            None,
            None,
            None,
            str(error),
        )

    if response.returncode != 0:
        detail = command_detail(response)
        sandbox.cleanup()
        return (
            None,
            None,
            None,
            detail,
        )

    mission_unit = (
        generated_systemd
        / MISSION_SERVICE
    )
    sandbox_environment = str(
        generated_environment
        / "truepanel-mission-control"
    )
    installed_environment = str(
        installed_environment_root
        / "truepanel-mission-control"
    )

    if mission_unit.is_file():
        unit_text = mission_unit.read_text(
            encoding="utf-8"
        )
        mission_unit.write_text(
            unit_text.replace(
                sandbox_environment,
                installed_environment,
            ),
            encoding="utf-8",
        )

    return (
        sandbox,
        generated_systemd,
        generated_environment,
        None,
    )


def print_action(
    action: str,
    target: str,
    detail: str,
) -> None:
    print(
        f"{action:<8} "
        f"{target:<32} "
        f"{detail}"
    )


def apply_postinit(
    action: str,
    task_id: int | None,
    payload: dict[str, Any],
    *,
    runner: Callable[..., Any] = run_command,
) -> tuple[bool, str]:
    if action == "none":
        return (
            True,
            f"Task {task_id}",
        )

    encoded = json.dumps(
        payload,
        separators=(",", ":"),
    )

    if action == "create":
        command = [
            "midclt",
            "call",
            "initshutdownscript.create",
            encoded,
        ]
    elif action == "update":
        if task_id is None:
            return (
                False,
                "Update requested without task ID",
            )

        command = [
            "midclt",
            "call",
            "initshutdownscript.update",
            str(task_id),
            encoded,
        ]
    else:
        return (
            False,
            f"Unknown action: {action}",
        )

    try:
        response = runner(
            command,
            timeout=20.0,
        )
    except (
        OSError,
        subprocess.SubprocessError,
    ) as error:
        return False, str(error)

    if response.returncode != 0:
        return (
            False,
            command_detail(response),
        )

    return (
        True,
        action,
    )


def run_systemctl(
    arguments: list[str],
    *,
    runner: Callable[..., Any] = run_command,
) -> tuple[bool, str]:
    try:
        response = runner(
            [
                "systemctl",
                *arguments,
            ],
            timeout=20.0,
        )
    except (
        OSError,
        subprocess.SubprocessError,
    ) as error:
        return False, str(error)

    if response.returncode != 0:
        return (
            False,
            command_detail(response),
        )

    return (
        True,
        response.stdout.strip() or "OK",
    )


def wait_for_services(
    *,
    runner: Callable[..., Any] = run_command,
    attempts: int = 10,
    delay: float = 0.5,
) -> bool:
    for _ in range(attempts):
        lcd_active, _ = service_state(
            LCD_SERVICE,
            "is-active",
            runner=runner,
        )
        mission_active, _ = service_state(
            MISSION_SERVICE,
            "is-active",
            runner=runner,
        )

        if (
            lcd_active
            and mission_active
        ):
            return True

        time.sleep(delay)

    return False


def run_repair(
    *,
    root: Path | None = None,
    dry_run: bool = False,
    runner: Callable[..., Any] = run_command,
    verifier: Callable[..., int] = run_verify,
) -> int:
    root = (
        root.resolve()
        if root is not None
        else project_root()
    )
    units_root = systemd_root()
    env_root = environment_root()

    print("\nTruePanel Lifecycle Repair")
    print("==========================\n")
    print(f"Installation: {root}")
    print(
        "Mode:         "
        + (
            "DRY RUN"
            if dry_run
            else "LIVE"
        )
    )
    print()

    required = (
        root / "truepanel.py",
        root / "truepanel.yaml",
        root / "start-truepanel.sh",
    )

    missing = [
        path
        for path in required
        if not path.is_file()
    ]

    if missing:
        for path in missing:
            print_action(
                "FAIL",
                "Installation",
                f"Missing: {path}",
            )

        print("\nRepair Result")
        print("-------------")
        print("FAIL")
        return 1

    (
        sandbox,
        generated_systemd,
        generated_environment,
        generation_error,
    ) = generate_lifecycle_files(
        root,
        runner=runner,
    )

    if generation_error is not None:
        print_action(
            "FAIL",
            "Lifecycle renderer",
            generation_error,
        )
        print("\nRepair Result")
        print("-------------")
        print("FAIL")
        return 1

    assert sandbox is not None
    assert generated_systemd is not None
    assert generated_environment is not None

    try:
        expected_lcd = (
            generated_systemd
            / LCD_SERVICE
        )
        expected_mission = (
            generated_systemd
            / MISSION_SERVICE
        )
        expected_environment = (
            generated_environment
            / "truepanel-mission-control"
        )

        installed_lcd = (
            units_root / LCD_SERVICE
        )
        installed_mission = (
            units_root / MISSION_SERVICE
        )
        installed_environment = (
            env_root
            / "truepanel-mission-control"
        )

        lcd_changed = files_differ(
            expected_lcd,
            installed_lcd,
        )
        mission_changed = files_differ(
            expected_mission,
            installed_mission,
        )
        environment_missing = (
            not installed_environment.is_file()
        )

        tasks, task_error = read_postinit_tasks(
            runner=runner,
        )

        if task_error is not None:
            print_action(
                "FAIL",
                "POSTINIT query",
                task_error,
            )
            print("\nRepair Result")
            print("-------------")
            print("FAIL")
            return 1

        assert tasks is not None

        (
            init_action,
            init_task_id,
            init_payload,
        ) = postinit_action(
            tasks,
            root,
        )

        lcd_active, lcd_state = (
            service_state(
                LCD_SERVICE,
                "is-active",
                runner=runner,
            )
        )
        mission_active, mission_state = (
            service_state(
                MISSION_SERVICE,
                "is-active",
                runner=runner,
            )
        )
        lcd_enabled, lcd_enable_state = (
            service_state(
                LCD_SERVICE,
                "is-enabled",
                runner=runner,
            )
        )
        (
            mission_enabled,
            mission_enable_state,
        ) = service_state(
            MISSION_SERVICE,
            "is-enabled",
            runner=runner,
        )

        print_action(
            (
                "REPAIR"
                if lcd_changed
                else "SKIP"
            ),
            "LCD service unit",
            str(installed_lcd),
        )
        print_action(
            (
                "REPAIR"
                if mission_changed
                else "SKIP"
            ),
            "Mission Control unit",
            str(installed_mission),
        )
        print_action(
            (
                "CREATE"
                if environment_missing
                else "PRESERVE"
            ),
            "Mission Control environment",
            str(installed_environment),
        )
        print_action(
            init_action.upper(),
            "POSTINIT restoration",
            (
                f"Task {init_task_id}"
                if init_task_id is not None
                else str(
                    init_payload["script"]
                )
            ),
        )
        print_action(
            (
                "SKIP"
                if lcd_enabled
                else "ENABLE"
            ),
            LCD_SERVICE,
            lcd_enable_state,
        )
        print_action(
            (
                "SKIP"
                if mission_enabled
                else "ENABLE"
            ),
            MISSION_SERVICE,
            mission_enable_state,
        )
        print_action(
            (
                "SKIP"
                if lcd_active
                else "START"
            ),
            LCD_SERVICE,
            lcd_state,
        )
        print_action(
            (
                "SKIP"
                if mission_active
                else "START"
            ),
            MISSION_SERVICE,
            mission_state,
        )

        if dry_run:
            print("\nRepair Result")
            print("-------------")
            print("DRY RUN COMPLETE")
            return 0

        if lcd_changed:
            install_file(
                expected_lcd,
                installed_lcd,
            )

        if mission_changed:
            install_file(
                expected_mission,
                installed_mission,
            )

        if environment_missing:
            install_file(
                expected_environment,
                installed_environment,
            )

        postinit_ok, postinit_detail = (
            apply_postinit(
                init_action,
                init_task_id,
                init_payload,
                runner=runner,
            )
        )

        if not postinit_ok:
            print_action(
                "FAIL",
                "POSTINIT restoration",
                postinit_detail,
            )
            print("\nRepair Result")
            print("-------------")
            print("FAIL")
            return 1

        units_changed = bool(
            lcd_changed
            or mission_changed
        )

        if units_changed:
            ok, detail = run_systemctl(
                ["daemon-reload"],
                runner=runner,
            )

            if not ok:
                print_action(
                    "FAIL",
                    "systemd reload",
                    detail,
                )
                return 1

        if (
            not lcd_enabled
            or not mission_enabled
        ):
            ok, detail = run_systemctl(
                [
                    "enable",
                    LCD_SERVICE,
                    MISSION_SERVICE,
                ],
                runner=runner,
            )

            if not ok:
                print_action(
                    "FAIL",
                    "systemd enable",
                    detail,
                )
                return 1

        restart_lcd = bool(
            lcd_changed
            or not lcd_active
        )
        restart_mission = bool(
            mission_changed
            or environment_missing
            or not mission_active
            or restart_lcd
        )

        if restart_lcd:
            ok, detail = run_systemctl(
                [
                    "restart",
                    LCD_SERVICE,
                ],
                runner=runner,
            )

            if not ok:
                print_action(
                    "FAIL",
                    LCD_SERVICE,
                    detail,
                )
                return 1

        if restart_mission:
            ok, detail = run_systemctl(
                [
                    "restart",
                    MISSION_SERVICE,
                ],
                runner=runner,
            )

            if not ok:
                print_action(
                    "FAIL",
                    MISSION_SERVICE,
                    detail,
                )
                return 1

        if (
            restart_lcd
            or restart_mission
        ):
            wait_for_services(
                runner=runner,
            )

    finally:
        sandbox.cleanup()

    print("\nPost-Repair Verification")
    print("------------------------")

    return verifier(
        root=root,
    )
