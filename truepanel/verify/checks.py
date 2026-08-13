"""
TruePanel installation verification.

These checks inspect the lifecycle contract without changing files,
services, configuration, or hardware state.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from truepanel import __version__
from truepanel.config.loader import load_config
from truepanel.paths import installation_root

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"


def result(
    status: str,
    name: str,
    detail: str,
) -> dict[str, str]:
    return {
        "status": status,
        "name": name,
        "detail": detail,
    }


def passed(
    name: str,
    detail: str = "Ready",
) -> dict[str, str]:
    return result(PASS, name, detail)


def warning(
    name: str,
    detail: str,
) -> dict[str, str]:
    return result(WARN, name, detail)


def failed(
    name: str,
    detail: str,
) -> dict[str, str]:
    return result(FAIL, name, detail)


def project_root() -> Path:
    """
    Resolve the installation root for verification.

    TRUEPANEL_VERIFY_ROOT remains supported as a
    compatibility override. Shared lifecycle path
    resolution is otherwise delegated to
    truepanel.paths.installation_root().
    """

    override = os.environ.get(
        "TRUEPANEL_VERIFY_ROOT"
    )

    if override:
        return installation_root(override)

    return installation_root()


def systemd_root() -> Path:
    return Path(
        os.environ.get(
            "TRUEPANEL_VERIFY_SYSTEMD_DIR",
            "/etc/systemd/system",
        )
    )


def environment_root() -> Path:
    return Path(
        os.environ.get(
            "TRUEPANEL_VERIFY_ENV_DIR",
            "/etc/default",
        )
    )


def mission_control_url() -> str:
    return os.environ.get(
        "TRUEPANEL_VERIFY_LCD_URL",
        "http://127.0.0.1:8787/api/v1/lcd",
    )


def check_installation_files(
    root: Path,
) -> list[dict[str, str]]:
    required = {
        "Launcher": root / "truepanel.py",
        "Configuration": root / "truepanel.yaml",
        "Startup restoration": (
            root / "start-truepanel.sh"
        ),
        "Deployment wrapper": (
            root / "deploy-truenas.sh"
        ),
    }

    results = []

    for name, path in required.items():
        if path.is_file():
            results.append(
                passed(name, str(path))
            )
        else:
            results.append(
                failed(
                    name,
                    f"Missing: {path}",
                )
            )

    return results


def check_package_version(
    root: Path,
) -> dict[str, str]:
    package = root / "truepanel" / "__init__.py"

    if not package.is_file():
        return failed(
            "Package version",
            f"Missing: {package}",
        )

    text = package.read_text(
        encoding="utf-8"
    )
    expected = (
        f'__version__ = "{__version__}"'
    )

    if expected not in text:
        return failed(
            "Package version",
            (
                f"Runtime={__version__}; "
                "deployment metadata differs"
            ),
        )

    return passed(
        "Package version",
        __version__,
    )


def check_configuration(
    root: Path,
) -> dict[str, str]:
    path = root / "truepanel.yaml"

    if not path.is_file():
        return failed(
            "Configuration",
            f"Missing: {path}",
        )

    try:
        config = load_config(path)
    except Exception as error:
        return failed(
            "Configuration",
            str(error),
        )

    if not isinstance(config, dict):
        return failed(
            "Configuration",
            "Configuration did not load as a mapping",
        )

    return passed(
        "Configuration",
        (
            "theme_pack="
            f"{config.get('theme_pack', 'default')}"
        ),
    )


def check_service_units(
    root: Path,
    units_root: Path,
    env_root: Path,
) -> list[dict[str, str]]:
    lcd_unit = (
        units_root / "truepanel.service"
    )
    mission_unit = (
        units_root
        / "truepanel-mission-control.service"
    )
    mission_env = (
        env_root
        / "truepanel-mission-control"
    )

    results = []

    if lcd_unit.is_file():
        text = lcd_unit.read_text(
            encoding="utf-8"
        )

        expected_root = str(root)
        lines = {
            line.strip()
            for line in text.splitlines()
            if line.strip()
        }

        wrapper_exec = (
            f"ExecStart={expected_root}/bin/truepanel run"
            in lines
        )
        direct_python_exec = any(
            line.startswith("ExecStart=")
            and line.endswith(
                f" {expected_root}/truepanel.py run"
            )
            for line in lines
        )

        if (
            f"WorkingDirectory={expected_root}"
            in lines
            and (
                wrapper_exec
                or direct_python_exec
            )
        ):
            results.append(
                passed(
                    "LCD service unit",
                    str(lcd_unit),
                )
            )
        else:
            results.append(
                failed(
                    "LCD service unit",
                    "Installed paths do not match deployment",
                )
            )
    else:
        results.append(
            failed(
                "LCD service unit",
                f"Missing: {lcd_unit}",
            )
        )

    if mission_unit.is_file():
        text = mission_unit.read_text(
            encoding="utf-8"
        )

        if (
            f"WorkingDirectory={root}"
            in text
            and "-m truepanel.web.service"
            in text
        ):
            results.append(
                passed(
                    "Mission Control unit",
                    str(mission_unit),
                )
            )
        else:
            results.append(
                failed(
                    "Mission Control unit",
                    "Installed paths do not match deployment",
                )
            )
    else:
        results.append(
            failed(
                "Mission Control unit",
                f"Missing: {mission_unit}",
            )
        )

    if mission_env.is_file():
        results.append(
            passed(
                "Mission Control environment",
                str(mission_env),
            )
        )
    else:
        results.append(
            failed(
                "Mission Control environment",
                f"Missing: {mission_env}",
            )
        )

    return results


def run_command(
    command: list[str],
    *,
    timeout: float = 5.0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def check_service_state(
    service: str,
    *,
    runner: Callable[..., Any] = run_command,
) -> dict[str, str]:
    try:
        response = runner(
            [
                "systemctl",
                "is-active",
                service,
            ],
            timeout=5.0,
        )
    except (
        OSError,
        subprocess.SubprocessError,
    ) as error:
        return failed(
            service,
            str(error),
        )

    state = (
        response.stdout.strip()
        or response.stderr.strip()
        or "unknown"
    )

    if response.returncode == 0:
        return passed(
            service,
            state,
        )

    return failed(
        service,
        state,
    )


def check_service_inactive(
    service: str,
    *,
    runner: Callable[..., Any] = run_command,
) -> dict[str, str]:
    """Require a service to be explicitly inactive."""

    try:
        response = runner(
            [
                "systemctl",
                "is-active",
                service,
            ],
            timeout=5.0,
        )
    except (
        OSError,
        subprocess.SubprocessError,
    ) as error:
        return failed(
            service,
            str(error),
        )

    state = (
        response.stdout.strip()
        or response.stderr.strip()
        or "unknown"
    )

    if state == "inactive":
        return passed(
            service,
            state,
        )

    return failed(
        service,
        (
            "Expected inactive; "
            f"observed {state}"
        ),
    )


def check_postinit(
    root: Path,
    *,
    runner: Callable[..., Any] = run_command,
) -> dict[str, str]:
    expected = str(
        root / "start-truepanel.sh"
    )

    try:
        response = runner(
            [
                "midclt",
                "call",
                "initshutdownscript.query",
            ],
            timeout=10.0,
        )
    except (
        OSError,
        subprocess.SubprocessError,
    ) as error:
        return failed(
            "POSTINIT restoration",
            str(error),
        )

    if response.returncode != 0:
        detail = (
            response.stderr.strip()
            or "midclt query failed"
        )
        return failed(
            "POSTINIT restoration",
            detail,
        )

    try:
        tasks = json.loads(
            response.stdout
        )
    except json.JSONDecodeError as error:
        return failed(
            "POSTINIT restoration",
            f"Invalid midclt response: {error}",
        )

    for task in tasks:
        if (
            task.get("type") == "SCRIPT"
            and task.get("script") == expected
            and task.get("when") == "POSTINIT"
            and task.get("enabled") is True
        ):
            return passed(
                "POSTINIT restoration",
                f"Task {task.get('id', 'unknown')}",
            )

    return failed(
        "POSTINIT restoration",
        f"No enabled task for {expected}",
    )


def fetch_json(
    url: str,
    *,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, Any]:
    with opener(
        url,
        timeout=5.0,
    ) as response:
        return json.load(response)


def check_mission_control_api(
    *,
    opener: Callable[..., Any] = urlopen,
) -> tuple[
    dict[str, str],
    dict[str, Any] | None,
]:
    url = mission_control_url()

    try:
        payload = fetch_json(
            url,
            opener=opener,
        )
    except (
        OSError,
        URLError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        return (
            failed(
                "Mission Control API",
                str(error),
            ),
            None,
        )

    lcd = payload.get("lcd")

    if not isinstance(lcd, dict):
        return (
            failed(
                "Mission Control API",
                "Response is missing LCD status",
            ),
            payload,
        )

    return (
        passed(
            "Mission Control API",
            url,
        ),
        payload,
    )


def check_lcd_transport(
    payload: dict[str, Any] | None,
) -> dict[str, str]:
    if payload is None:
        return failed(
            "LCD transport",
            "Mission Control API unavailable",
        )

    lcd = payload.get("lcd", {})
    reader = lcd.get("reader", {})

    if not isinstance(reader, dict):
        return failed(
            "LCD transport",
            "Reader status unavailable",
        )

    healthy = bool(
        reader.get("healthy", False)
    )
    connected = bool(
        reader.get("connected", False)
    )
    reader_alive = bool(
        reader.get("thread_alive", False)
    )
    dispatcher_alive = bool(
        reader.get(
            "dispatcher_alive",
            False,
        )
    )

    detail = (
        f"port={reader.get('port', 'unknown')} "
        f"baud={reader.get('speed', 'unknown')} "
        f"errors={reader.get('reader_errors', 0)}"
    )

    if (
        healthy
        and connected
        and reader_alive
        and dispatcher_alive
    ):
        return passed(
            "LCD transport",
            detail,
        )

    return failed(
        "LCD transport",
        detail,
    )


def run_checks(
    *,
    root: Path | None = None,
    runner: Callable[..., Any] = run_command,
    opener: Callable[..., Any] = urlopen,
) -> list[dict[str, str]]:
    root = (
        root.resolve()
        if root is not None
        else project_root()
    )

    results = []
    results.extend(
        check_installation_files(root)
    )
    results.append(
        check_package_version(root)
    )
    results.append(
        check_configuration(root)
    )
    results.extend(
        check_service_units(
            root,
            systemd_root(),
            environment_root(),
        )
    )
    results.append(
        check_service_state(
            "truepanel.service",
            runner=runner,
        )
    )
    results.append(
        check_service_state(
            "truepanel-mission-control.service",
            runner=runner,
        )
    )
    results.append(
        check_service_inactive(
            "truepanel-host-agent.service",
            runner=runner,
        )
    )
    results.append(
        check_postinit(
            root,
            runner=runner,
        )
    )

    api_result, payload = (
        check_mission_control_api(
            opener=opener,
        )
    )
    results.append(api_result)
    results.append(
        check_lcd_transport(payload)
    )

    return results


def print_result(
    check: dict[str, str],
) -> None:
    print(
        f"{check['status']:<5} "
        f"{check['name']:<30} "
        f"{check['detail']}"
    )


def run_verify(
    *,
    root: Path | None = None,
    runner: Callable[..., Any] = run_command,
    opener: Callable[..., Any] = urlopen,
) -> int:
    print("\nTruePanel Installation Verification")
    print("===================================\n")

    checks = run_checks(
        root=root,
        runner=runner,
        opener=opener,
    )

    for check in checks:
        print_result(check)

    failures = [
        check
        for check in checks
        if check["status"] == FAIL
    ]
    warnings = [
        check
        for check in checks
        if check["status"] == WARN
    ]

    print("\nVerification Result")
    print("-------------------")

    if failures:
        print(
            f"FAIL ({len(failures)} failed, "
            f"{len(warnings)} warnings)"
        )
        return 1

    if warnings:
        print(
            f"PASS WITH WARNINGS "
            f"({len(warnings)} warnings)"
        )
        return 0

    print("PASS")
    return 0
