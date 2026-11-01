"""Manage TruePanel's TrueNAS-supported i2c-dev boot preload.

TrueNAS persists init/shutdown tasks in its configuration database.  Using the
middleware API keeps the preload across appliance-generated operating-system
state without placing an unmanaged file in ``/etc/modules-load.d``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

TASK_COMMENT = "TruePanel managed: load i2c-dev for front-panel SMBus"
TASK_COMMAND = "/sbin/modprobe i2c-dev"
TASK_WHEN = "POSTINIT"
TASK_TIMEOUT = 10
MODULE_NAME = "i2c-dev"


class LifecycleError(RuntimeError):
    """Raised when the managed TrueNAS lifecycle contract cannot be proven."""


def _tool(name: str, override_env: str) -> str:
    override = os.environ.get(override_env)
    if override:
        return override

    resolved = shutil.which(name)
    if resolved:
        return resolved

    raise LifecycleError(
        f"Required TrueNAS lifecycle command is unavailable: {name}"
    )


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=True,
            text=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "no command output").strip()
        raise LifecycleError(
            f"Command failed ({' '.join(command[:3])}): {detail}"
        ) from exc


def _midclt_call(method: str, *arguments: object) -> Any:
    midclt = _tool("midclt", "TRUEPANEL_MIDCLT_BIN")
    command = [midclt, "call", method]
    for argument in arguments:
        if isinstance(argument, (dict, list, bool)) or argument is None:
            command.append(json.dumps(argument, separators=(",", ":")))
        else:
            command.append(str(argument))

    result = _run(command)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise LifecycleError(
            f"TrueNAS middleware returned invalid JSON for {method}"
        ) from exc


def _query_tasks() -> list[dict[str, Any]]:
    result = _midclt_call("initshutdownscript.query")
    if not isinstance(result, list) or not all(
        isinstance(item, dict) for item in result
    ):
        raise LifecycleError(
            "TrueNAS middleware returned an invalid init/shutdown task list"
        )
    return result


def _desired_task() -> dict[str, Any]:
    return {
        "type": "COMMAND",
        "command": TASK_COMMAND,
        "script": "",
        "when": TASK_WHEN,
        "enabled": True,
        "timeout": TASK_TIMEOUT,
        "comment": TASK_COMMENT,
    }


def _is_equivalent(task: dict[str, Any]) -> bool:
    return (
        str(task.get("type", "")).upper() == "COMMAND"
        and task.get("command") == TASK_COMMAND
        and str(task.get("when", "")).upper() == TASK_WHEN
        and task.get("enabled") is True
    )


def _owned_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [task for task in tasks if task.get("comment") == TASK_COMMENT]


def _assert_owned_task(task: dict[str, Any]) -> None:
    desired = _desired_task()
    for field in (
        "type",
        "command",
        "when",
        "enabled",
        "timeout",
        "comment",
    ):
        actual = task.get(field)
        expected = desired[field]
        if field in {"type", "when"}:
            actual = str(actual).upper()
        if actual != expected:
            raise LifecycleError(
                "TruePanel's managed i2c-dev POSTINIT task failed "
                f"verification for field {field}"
            )


def _module_path() -> Path:
    return Path(
        os.environ.get(
            "TRUEPANEL_I2C_MODULE_PATH",
            "/sys/module/i2c_dev",
        )
    )


def load_module() -> None:
    modprobe = _tool("modprobe", "TRUEPANEL_MODPROBE_BIN")
    _run([modprobe, MODULE_NAME])
    if not _module_path().is_dir():
        raise LifecycleError(
            "modprobe completed but the i2c-dev kernel module is not visible"
        )


def ensure_persistence() -> str:
    """Load i2c-dev now and ensure a persistent TrueNAS POSTINIT task."""

    load_module()
    tasks = _query_tasks()
    owned = _owned_tasks(tasks)

    if len(owned) > 1:
        raise LifecycleError(
            "Multiple TruePanel-managed i2c-dev POSTINIT tasks exist; "
            "refusing to guess which record owns the lifecycle contract"
        )

    if owned:
        task_id = owned[0].get("id")
        if not isinstance(task_id, int):
            raise LifecycleError(
                "TruePanel's managed i2c-dev POSTINIT task has no valid id"
            )
        if not _is_equivalent(owned[0]) or owned[0].get("timeout") != TASK_TIMEOUT:
            _midclt_call(
                "initshutdownscript.update",
                task_id,
                _desired_task(),
            )
            action = "updated"
        else:
            action = "preserved"
    elif any(_is_equivalent(task) for task in tasks):
        action = "external"
    else:
        _midclt_call(
            "initshutdownscript.create",
            _desired_task(),
        )
        action = "created"

    verified = _query_tasks()
    owned = _owned_tasks(verified)
    if owned:
        if len(owned) != 1:
            raise LifecycleError(
                "TruePanel's managed i2c-dev POSTINIT task is not unique"
            )
        _assert_owned_task(owned[0])
    elif not any(_is_equivalent(task) for task in verified):
        raise LifecycleError(
            "No enabled TrueNAS POSTINIT task loads i2c-dev after installation"
        )

    return action


def verify_persistence() -> str:
    tasks = _query_tasks()
    owned = _owned_tasks(tasks)
    if len(owned) > 1:
        raise LifecycleError(
            "TruePanel's managed i2c-dev POSTINIT task is not unique"
        )
    if owned:
        _assert_owned_task(owned[0])
        return "managed"
    if any(_is_equivalent(task) for task in tasks):
        return "external"
    raise LifecycleError(
        "No enabled TrueNAS POSTINIT task loads i2c-dev"
    )


def remove_persistence() -> int:
    """Remove only tasks carrying TruePanel's explicit ownership marker."""

    owned = _owned_tasks(_query_tasks())
    for task in owned:
        task_id = task.get("id")
        if not isinstance(task_id, int):
            raise LifecycleError(
                "TruePanel's managed i2c-dev POSTINIT task has no valid id"
            )
        _midclt_call("initshutdownscript.delete", task_id)

    if _owned_tasks(_query_tasks()):
        raise LifecycleError(
            "TruePanel-managed i2c-dev POSTINIT task remains after removal"
        )
    return len(owned)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage TruePanel's TrueNAS i2c-dev boot preload",
    )
    parser.add_argument(
        "action",
        choices=("ensure", "verify", "remove"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.action == "ensure":
            action = ensure_persistence()
            print(
                "i2c-dev is loaded; TrueNAS POSTINIT persistence "
                f"is verified ({action})."
            )
        elif args.action == "verify":
            owner = verify_persistence()
            print(
                "TrueNAS POSTINIT i2c-dev persistence is verified "
                f"({owner})."
            )
        else:
            removed = remove_persistence()
            print(
                "Removed "
                f"{removed} TruePanel-managed i2c-dev POSTINIT task(s)."
            )
    except LifecycleError as exc:
        print(f"TrueNAS i2c-dev lifecycle error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
