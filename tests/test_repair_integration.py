import json
import subprocess
from pathlib import Path

from truepanel.repair.checks import run_repair


class Result:
    def __init__(
        self,
        returncode=0,
        stdout="",
        stderr="",
    ):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class RepairHarness:
    def __init__(self, root: Path):
        self.root = root
        self.tasks = [
            {
                "id": 8,
                "type": "SCRIPT",
                "command": "",
                "script": "/old/TruePanel/start-truepanel.sh",
                "when": "POSTINIT",
                "enabled": False,
                "timeout": 10,
                "comment": "TruePanel",
            }
        ]
        self.active = {
            "truepanel.service": False,
            "truepanel-mission-control.service": False,
        }
        self.enabled = {
            "truepanel.service": False,
            "truepanel-mission-control.service": False,
        }
        self.commands = []

    def __call__(
        self,
        command,
        *,
        timeout=15.0,
        env=None,
    ):
        self.commands.append(list(command))

        if command[0] == "bash":
            return subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )

        if command[:3] == [
            "midclt",
            "call",
            "initshutdownscript.query",
        ]:
            return Result(
                stdout=json.dumps(self.tasks)
            )

        if command[:3] == [
            "midclt",
            "call",
            "initshutdownscript.update",
        ]:
            task_id = int(command[3])
            payload = json.loads(command[4])

            for index, task in enumerate(self.tasks):
                if task["id"] == task_id:
                    self.tasks[index] = {
                        **payload,
                        "id": task_id,
                    }
                    break

            return Result(
                stdout=json.dumps(
                    self.tasks[index]
                )
            )

        if command[:3] == [
            "midclt",
            "call",
            "initshutdownscript.create",
        ]:
            payload = json.loads(command[3])
            task = {
                **payload,
                "id": 99,
            }
            self.tasks.append(task)

            return Result(
                stdout=json.dumps(task)
            )

        if command[:2] == [
            "systemctl",
            "is-active",
        ]:
            service = command[2]

            return Result(
                returncode=(
                    0
                    if self.active[service]
                    else 3
                ),
                stdout=(
                    "active\n"
                    if self.active[service]
                    else "inactive\n"
                ),
            )

        if command[:2] == [
            "systemctl",
            "is-enabled",
        ]:
            service = command[2]

            return Result(
                returncode=(
                    0
                    if self.enabled[service]
                    else 1
                ),
                stdout=(
                    "enabled\n"
                    if self.enabled[service]
                    else "disabled\n"
                ),
            )

        if command[:2] == [
            "systemctl",
            "daemon-reload",
        ]:
            return Result()

        if command[:2] == [
            "systemctl",
            "enable",
        ]:
            for service in command[2:]:
                self.enabled[service] = True

            return Result()

        if command[:2] == [
            "systemctl",
            "restart",
        ]:
            for service in command[2:]:
                self.active[service] = True

            return Result()

        raise AssertionError(
            f"Unexpected command: {command}"
        )


def create_broken_installation(
    root: Path,
):
    (root / "truepanel").mkdir(
        parents=True
    )
    (root / "truepanel.py").write_text(
        "# launcher\n"
    )
    (root / "truepanel.yaml").write_text(
        "theme_pack: tactical\n"
    )
    (
        root
        / "truepanel"
        / "__init__.py"
    ).write_text(
        '__version__ = "1.1.0"\n'
    )

    startup = root / "start-truepanel.sh"
    startup.write_text(
        """#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
  pwd
)"

SYSTEMD_DIR="${TRUEPANEL_SYSTEMD_DIR}"
ENV_DIR="${TRUEPANEL_ENV_DIR}"

mkdir -p "$SYSTEMD_DIR" "$ENV_DIR"

cat > "$ENV_DIR/truepanel-mission-control" <<ENV
TRUEPANEL_MC_HOST=0.0.0.0
TRUEPANEL_MC_PORT=8787
TRUEPANEL_MC_CONFIG_PATH=$ROOT_DIR/truepanel.yaml
TRUEPANEL_MC_ALLOW_CONFIG_WRITES=false
ENV

cat > "$SYSTEMD_DIR/truepanel.service" <<SERVICE
[Unit]
Description=TruePanel QNAP LCD Front Panel

[Service]
WorkingDirectory=$ROOT_DIR
ExecStart=/usr/bin/python3 $ROOT_DIR/truepanel.py run

[Install]
WantedBy=multi-user.target
SERVICE

cat > "$SYSTEMD_DIR/truepanel-mission-control.service" <<SERVICE
[Unit]
Description=TruePanel Mission Control Web Dashboard

[Service]
WorkingDirectory=$ROOT_DIR
EnvironmentFile=-$ENV_DIR/truepanel-mission-control
ExecStart=/usr/bin/python3 -m truepanel.web.service

[Install]
WantedBy=multi-user.target
SERVICE
"""
    )
    startup.chmod(0o755)


def test_repair_restores_broken_lifecycle(
    tmp_path,
    monkeypatch,
):
    root = tmp_path / "TruePanel"
    systemd = tmp_path / "systemd"
    environment = tmp_path / "default"

    create_broken_installation(root)

    monkeypatch.setenv(
        "TRUEPANEL_VERIFY_SYSTEMD_DIR",
        str(systemd),
    )
    monkeypatch.setenv(
        "TRUEPANEL_VERIFY_ENV_DIR",
        str(environment),
    )

    harness = RepairHarness(root)
    verified = {}

    def verifier(**kwargs):
        verified.update(kwargs)
        return 0

    code = run_repair(
        root=root,
        runner=harness,
        verifier=verifier,
    )

    assert code == 0

    lcd_unit = (
        systemd / "truepanel.service"
    )
    mission_unit = (
        systemd
        / "truepanel-mission-control.service"
    )
    mission_env = (
        environment
        / "truepanel-mission-control"
    )

    assert lcd_unit.is_file()
    assert mission_unit.is_file()
    assert mission_env.is_file()

    assert (
        f"WorkingDirectory={root}"
        in lcd_unit.read_text()
    )
    assert (
        f"WorkingDirectory={root}"
        in mission_unit.read_text()
    )
    assert (
        f"EnvironmentFile=-{mission_env}"
        in mission_unit.read_text()
    )

    task = harness.tasks[0]

    assert task == {
        "id": 8,
        "type": "SCRIPT",
        "command": "",
        "script": str(
            root / "start-truepanel.sh"
        ),
        "when": "POSTINIT",
        "enabled": True,
        "timeout": 30,
        "comment": "TruePanel",
    }

    assert all(
        harness.enabled.values()
    )
    assert all(
        harness.active.values()
    )

    assert [
        "systemctl",
        "daemon-reload",
    ] in harness.commands

    assert [
        "systemctl",
        "enable",
        "truepanel.service",
        "truepanel-mission-control.service",
    ] in harness.commands

    assert [
        "systemctl",
        "restart",
        "truepanel.service",
    ] in harness.commands

    assert [
        "systemctl",
        "restart",
        "truepanel-mission-control.service",
    ] in harness.commands

    assert verified == {
        "root": root.resolve()
    }


def test_dry_run_does_not_change_broken_lifecycle(
    tmp_path,
    monkeypatch,
):
    root = tmp_path / "TruePanel"
    systemd = tmp_path / "systemd"
    environment = tmp_path / "default"

    create_broken_installation(root)

    monkeypatch.setenv(
        "TRUEPANEL_VERIFY_SYSTEMD_DIR",
        str(systemd),
    )
    monkeypatch.setenv(
        "TRUEPANEL_VERIFY_ENV_DIR",
        str(environment),
    )

    harness = RepairHarness(root)

    code = run_repair(
        root=root,
        dry_run=True,
        runner=harness,
        verifier=lambda **kwargs: 9,
    )

    assert code == 0
    assert not systemd.exists()
    assert not environment.exists()

    assert harness.tasks[0]["enabled"] is False
    assert not any(
        command[:2]
        in (
            ["systemctl", "enable"],
            ["systemctl", "restart"],
            ["systemctl", "daemon-reload"],
        )
        for command in harness.commands
    )
