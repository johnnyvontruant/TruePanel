import argparse
import json
from pathlib import Path

from truepanel.host.commands import (
    add_host_subcommands,
    handle_host_command,
    run_host_readiness,
)
from truepanel.host.readiness import (
    collect_host_readiness,
)


SERVICE_TEXT = """[Unit]
Description=TruePanel Privileged Host Agent (standalone activation locked)
After=local-fs.target
ConditionPathExists=/run/truepanel/standalone-host-agent.enabled

[Service]
Type=simple
WorkingDirectory=/opt/truepanel
ExecStart=/opt/truepanel/.venv/bin/python -m truepanel.host.agent
Restart=on-failure
RestartSec=5
TimeoutStopSec=15
UMask=0027
"""


def install_service(root: Path, text: str = SERVICE_TEXT) -> Path:
    path = (
        root
        / "etc/systemd/system/truepanel-host-agent.service"
    )
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_text(
        text,
        encoding="utf-8",
    )
    return path


def check_map(report):
    return {
        check.name: check
        for check in report.checks
    }


def test_ready_dormant_install_passes(tmp_path):
    install_service(tmp_path)

    report = collect_host_readiness(
        root=tmp_path,
        activation_enabled=False,
    )
    checks = check_map(report)

    assert report.prepared_safely is True
    assert report.activation_state == "locked"
    assert all(
        check.passed
        for check in checks.values()
    )

    payload = report.to_dict()
    assert payload["schema_version"] == 1
    assert payload["prepared_safely"] is True
    assert payload["activation_state"] == "locked"
    assert payload["service_unit_path"] == (
        "/etc/systemd/system/truepanel-host-agent.service"
    )
    assert payload["cutover_marker_path"] == (
        "/run/truepanel/standalone-host-agent.enabled"
    )


def test_missing_service_requires_review(tmp_path):
    report = collect_host_readiness(
        root=tmp_path,
        activation_enabled=False,
    )
    checks = check_map(report)

    assert report.prepared_safely is False
    assert checks["service_unit_installed"].passed is False
    assert checks["service_exec_target"].passed is False
    assert checks["systemd_condition_gate"].passed is False
    assert checks["service_not_enableable"].passed is False


def test_marker_present_requires_review(tmp_path):
    install_service(tmp_path)
    marker = (
        tmp_path
        / "run/truepanel/standalone-host-agent.enabled"
    )
    marker.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    marker.write_text("armed\n", encoding="utf-8")

    report = collect_host_readiness(
        root=tmp_path,
        activation_enabled=False,
    )
    checks = check_map(report)

    assert report.prepared_safely is False
    assert checks["cutover_marker_absent"].passed is False


def test_unlocked_python_gate_requires_review(tmp_path):
    install_service(tmp_path)

    report = collect_host_readiness(
        root=tmp_path,
        activation_enabled=True,
    )
    checks = check_map(report)

    assert report.prepared_safely is False
    assert report.activation_state == "unlocked"
    assert checks["python_activation_locked"].passed is False


def test_malformed_service_requires_review(tmp_path):
    install_service(
        tmp_path,
        text="""[Unit]
Description=Unsafe Host Agent

[Service]
ExecStart=/bin/false

[Install]
WantedBy=multi-user.target
""",
    )

    report = collect_host_readiness(
        root=tmp_path,
        activation_enabled=False,
    )
    checks = check_map(report)

    assert report.prepared_safely is False
    assert checks["service_unit_installed"].passed is True
    assert checks["service_exec_target"].passed is False
    assert checks["systemd_condition_gate"].passed is False
    assert checks["service_not_enableable"].passed is False


def test_readiness_command_outputs_json_and_success(tmp_path, capsys):
    install_service(tmp_path)

    result = run_host_readiness(
        json_output=True,
        root=tmp_path,
    )

    payload = json.loads(
        capsys.readouterr().out
    )

    assert result == 0
    assert payload["prepared_safely"] is True
    assert payload["activation_state"] == "locked"


def test_readiness_command_returns_review_exit_code(tmp_path, capsys):
    result = run_host_readiness(
        json_output=False,
        root=tmp_path,
    )

    output = capsys.readouterr().out

    assert result == 1
    assert "Prepared safely: NO" in output
    assert "Standalone activation: LOCKED" in output


def test_host_parser_registers_readiness_command(tmp_path):
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(
        dest="command"
    )
    add_host_subcommands(subcommands)

    args = parser.parse_args(
        [
            "host",
            "readiness",
            "--root",
            str(tmp_path),
            "--json",
        ]
    )

    assert args.command == "host"
    assert args.host_command == "readiness"
    assert args.host_readiness_root == str(tmp_path)
    assert args.host_readiness_json is True


def test_host_dispatch_routes_readiness_command(tmp_path, capsys):
    install_service(tmp_path)

    args = argparse.Namespace(
        command="host",
        host_command="readiness",
        host_readiness_root=str(tmp_path),
        host_readiness_json=True,
    )

    result = handle_host_command(args)
    payload = json.loads(
        capsys.readouterr().out
    )

    assert result == 0
    assert payload["prepared_safely"] is True


def test_readiness_module_is_strictly_passive():
    source = Path(
        "truepanel/host/readiness.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "fcntl",
        "flock",
        "HostOwnershipGuard",
        "host-owner.lock",
        "subprocess",
        "systemctl",
        ".write_text(",
        ".touch(",
        ".mkdir(",
        ".unlink(",
        "os.remove(",
    ):
        assert forbidden not in source
