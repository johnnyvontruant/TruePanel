import argparse
import json
from pathlib import Path

from truepanel.host.commands import (
    add_host_subcommands,
    handle_host_command,
)


def test_host_parser_registers_acceptance_command():
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command")
    add_host_subcommands(subcommands)

    args = parser.parse_args(
        [
            "host",
            "acceptance",
            "--root",
            "/tmp/root",
            "--config",
            "/tmp/truepanel.yaml",
            "--json",
        ]
    )

    assert args.command == "host"
    assert args.host_command == "acceptance"
    assert args.host_acceptance_root == "/tmp/root"
    assert args.host_acceptance_config == "/tmp/truepanel.yaml"
    assert args.host_acceptance_json is True


def test_acceptance_dispatch_forwards_root_config_and_json(monkeypatch):
    calls = []

    def fake_run_host_acceptance(**kwargs):
        calls.append(kwargs)
        return 7

    monkeypatch.setattr(
        "truepanel.host.commands.run_host_acceptance",
        fake_run_host_acceptance,
    )

    args = argparse.Namespace(
        command="host",
        host_command="acceptance",
        host_acceptance_root="/tmp/root",
        host_acceptance_config="/tmp/config.yaml",
        host_acceptance_json=True,
    )

    result = handle_host_command(args)

    assert result == 7
    assert calls == [
        {
            "json_output": True,
            "root": Path("/tmp/root").resolve(),
            "config_path": "/tmp/config.yaml",
        }
    ]


def test_acceptance_command_contract_is_passive():
    source = Path(
        "truepanel/host/commands.py"
    ).read_text(encoding="utf-8")

    start = source.index("def run_host_acceptance(")
    end = source.index("\ndef ", start + 1)
    block = source[start:end]

    assert "collect_host_readiness(" in block
    assert "collect_host_fan_safety(" in block
    assert "build_host_acceptance_report(" in block

    for forbidden in (
        "subprocess",
        "systemctl",
        "write_text(",
        "request_profile(",
        "HostOwnershipGuard",
    ):
        assert forbidden not in block
