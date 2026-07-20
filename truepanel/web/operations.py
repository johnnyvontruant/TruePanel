"""Operator commands for the Mission Control companion service."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping
from urllib.error import URLError
from urllib.request import urlopen


SERVICE_NAME = "truepanel-mission-control"
DEFAULT_ENV_PATH = Path("/etc/default/truepanel-mission-control")


@dataclass(frozen=True)
class MissionControlStatus:
    loaded: str
    enabled: str
    active: str
    substate: str
    host: str
    port: int
    writes_enabled: bool
    url: str
    health: str


    def as_dict(self):
        return {
            "loaded": self.loaded,
            "enabled": self.enabled,
            "active": self.active,
            "substate": self.substate,
            "host": self.host,
            "port": self.port,
            "writes_enabled": self.writes_enabled,
            "url": self.url,
            "health": self.health,
        }


def read_environment(path=DEFAULT_ENV_PATH):
    values = {}
    candidate = Path(path)

    if not candidate.exists():
        return values

    for raw_line in candidate.read_text(
        encoding="utf-8",
    ).splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#"):
            continue

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()

    return values


def environment_settings(values: Mapping[str, str]):
    host = values.get(
        "TRUEPANEL_MC_HOST",
        "127.0.0.1",
    )

    raw_port = values.get(
        "TRUEPANEL_MC_PORT",
        "8787",
    )

    try:
        port = int(raw_port)
    except ValueError:
        port = 8787

    raw_writes = values.get(
        "TRUEPANEL_MC_ALLOW_CONFIG_WRITES",
        "false",
    ).strip().lower()

    writes_enabled = raw_writes in {
        "1",
        "true",
        "yes",
        "on",
    }

    display_host = host

    if host in {"0.0.0.0", "::"}:
        display_host = "<BattleStation-IP>"

    url = f"http://{display_host}:{port}"

    return host, port, writes_enabled, url


def systemd_properties(
    runner: Callable = subprocess.run,
):
    command = [
        "systemctl",
        "show",
        SERVICE_NAME,
        "--property=LoadState",
        "--property=UnitFileState",
        "--property=ActiveState",
        "--property=SubState",
    ]

    try:
        result = runner(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return {
            "LoadState": "unavailable",
            "UnitFileState": "unavailable",
            "ActiveState": "unavailable",
            "SubState": "unavailable",
        }

    properties = {}

    for line in result.stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        properties[key] = value

    return properties


def health_status(
    host: str,
    port: int,
    opener=urlopen,
):
    probe_host = host

    if host in {"0.0.0.0", "::"}:
        probe_host = "127.0.0.1"

    address = f"http://{probe_host}:{port}/healthz"

    try:
        with opener(address, timeout=3) as response:
            payload = json.load(response)
    except (
        OSError,
        URLError,
        ValueError,
        json.JSONDecodeError,
    ):
        return "unreachable"

    if payload.get("status") == "ok":
        return "healthy"

    return "degraded"


def get_status(
    env_path=DEFAULT_ENV_PATH,
    runner: Callable = subprocess.run,
    opener=urlopen,
):
    values = read_environment(env_path)
    host, port, writes_enabled, url = (
        environment_settings(values)
    )
    properties = systemd_properties(runner)

    health = "not running"

    if properties.get("ActiveState") == "active":
        health = health_status(
            host,
            port,
            opener=opener,
        )

    return MissionControlStatus(
        loaded=properties.get(
            "LoadState",
            "unknown",
        ),
        enabled=properties.get(
            "UnitFileState",
            "unknown",
        ),
        active=properties.get(
            "ActiveState",
            "unknown",
        ),
        substate=properties.get(
            "SubState",
            "unknown",
        ),
        host=host,
        port=port,
        writes_enabled=writes_enabled,
        url=url,
        health=health,
    )


def print_status(status: MissionControlStatus):
    write_mode = (
        "guarded writes enabled"
        if status.writes_enabled
        else "read only"
    )

    print()
    print("TruePanel Mission Control")
    print("=========================")
    print(f"Service:  {status.active} / {status.substate}")
    print(f"Enabled:  {status.enabled}")
    print(f"Loaded:   {status.loaded}")
    print(f"Health:   {status.health}")
    print(f"Bind:     {status.host}:{status.port}")
    print(f"URL:      {status.url}")
    print(f"Config:   {write_mode}")


def run_systemctl(action, runner: Callable = subprocess.run):
    result = runner(
        ["systemctl", action, SERVICE_NAME],
        check=False,
    )

    return int(result.returncode)


def run_logs(runner: Callable = subprocess.run):
    result = runner(
        [
            "journalctl",
            "-u",
            SERVICE_NAME,
            "-f",
        ],
        check=False,
    )

    return int(result.returncode)


def add_mission_control_subcommands(subcommands):
    command = subcommands.add_parser(
        "mission-control",
        help="Operate the Mission Control web service",
    )

    actions = command.add_subparsers(
        dest="mission_control_action",
    )

    actions.add_parser(
        "status",
        help="Show service and health status",
    )
    actions.add_parser(
        "start",
        help="Start Mission Control",
    )
    actions.add_parser(
        "stop",
        help="Stop Mission Control",
    )
    actions.add_parser(
        "restart",
        help="Restart Mission Control",
    )
    actions.add_parser(
        "logs",
        help="Follow Mission Control logs",
    )

    return command


def handle_mission_control_command(args):
    if args.command != "mission-control":
        return None

    action = args.mission_control_action or "status"

    if action == "status":
        status = get_status()
        print_status(status)
        return (
            0
            if status.health == "healthy"
            else 1
        )

    if action == "logs":
        return run_logs()

    return run_systemctl(action)
