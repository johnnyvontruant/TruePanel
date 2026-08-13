import argparse
import json

import truepanel.host.commands as commands
from truepanel.host.readiness import (
    HostReadinessCheck,
    HostReadinessReport,
)


def readiness(*, prepared=True):
    checks = (
        HostReadinessCheck(
            "python_activation_locked",
            True,
            "locked",
        ),
        HostReadinessCheck(
            "deployment_safe",
            prepared,
            "safe" if prepared else "review",
        ),
    )

    return HostReadinessReport(
        root="/",
        checks=checks,
    )


def test_host_parser_registers_cutover_plan_command():
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(
        dest="command"
    )
    commands.add_host_subcommands(subcommands)

    args = parser.parse_args(
        [
            "host",
            "cutover-plan",
            "--root",
            "/tmp/truepanel-root",
            "--json",
        ]
    )

    assert args.command == "host"
    assert args.host_command == "cutover-plan"
    assert args.host_cutover_root == "/tmp/truepanel-root"
    assert args.host_cutover_json is True


def test_cutover_plan_command_outputs_non_executable_json(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        commands,
        "collect_host_readiness",
        lambda **kwargs: readiness(),
    )

    result = commands.run_host_cutover_plan(
        json_output=True,
    )
    payload = json.loads(
        capsys.readouterr().out
    )

    assert result == 0
    assert payload["prepared_safely"] is True
    assert payload["activation_state"] == "locked"
    assert payload["execution_enabled"] is False
    assert len(payload["cutover_steps"]) == 6
    assert len(payload["rollback_steps"]) == 4


def test_cutover_plan_command_returns_review_when_unprepared(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        commands,
        "collect_host_readiness",
        lambda **kwargs: readiness(prepared=False),
    )

    result = commands.run_host_cutover_plan(
        json_output=False,
    )
    output = capsys.readouterr().out

    assert result == 1
    assert "Dormant deployment prepared safely: NO" in output
    assert "Cutover execution: DISABLED" in output


def test_host_dispatch_routes_cutover_plan(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        commands,
        "collect_host_readiness",
        lambda **kwargs: readiness(),
    )

    args = argparse.Namespace(
        command="host",
        host_command="cutover-plan",
        host_cutover_root=None,
        host_cutover_json=True,
    )

    result = commands.handle_host_command(args)
    payload = json.loads(
        capsys.readouterr().out
    )

    assert result == 0
    assert payload["execution_enabled"] is False
