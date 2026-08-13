import io
import json
from pathlib import Path

from truepanel.verify.checks import (
    FAIL,
    PASS,
    check_installation_files,
    check_lcd_transport,
    check_postinit,
    check_service_inactive,
    check_service_state,
    check_service_units,
    run_verify,
)


class CommandResult:
    def __init__(
        self,
        returncode=0,
        stdout="",
        stderr="",
    ):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return io.StringIO(
            json.dumps(self.payload)
        )

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        return False


def create_installation(root: Path):
    (root / "truepanel").mkdir()
    (root / "truepanel.py").write_text("")
    (root / "truepanel.yaml").write_text(
        "theme_pack: default\n"
    )
    (root / "start-truepanel.sh").write_text("")
    (root / "deploy-truenas.sh").write_text("")
    (
        root / "truepanel" / "__init__.py"
    ).write_text(
        '__version__ = "1.1.0"\n'
    )


def test_installation_files_pass(
    tmp_path,
):
    create_installation(tmp_path)

    results = check_installation_files(
        tmp_path
    )

    assert all(
        item["status"] == PASS
        for item in results
    )


def test_installation_files_report_missing(
    tmp_path,
):
    results = check_installation_files(
        tmp_path
    )

    assert all(
        item["status"] == FAIL
        for item in results
    )


def _write_valid_service_scaffolding(
    root: Path,
    units: Path,
    env: Path,
    *,
    lcd_exec: str,
):
    units.mkdir()
    env.mkdir()

    (units / "truepanel.service").write_text(
        (
            "[Service]\n"
            f"WorkingDirectory={root}\n"
            f"ExecStart={lcd_exec}\n"
        ),
        encoding="utf-8",
    )

    (
        units
        / "truepanel-mission-control.service"
    ).write_text(
        (
            "[Service]\n"
            f"WorkingDirectory={root}\n"
            "ExecStart=/usr/bin/python3 "
            "-m truepanel.web.service\n"
        ),
        encoding="utf-8",
    )

    (
        env
        / "truepanel-mission-control"
    ).write_text(
        "",
        encoding="utf-8",
    )


def test_service_units_accept_installer_cli_wrapper(
    tmp_path,
):
    root = tmp_path / "install"
    units = tmp_path / "systemd"
    env = tmp_path / "default"
    root.mkdir()

    _write_valid_service_scaffolding(
        root,
        units,
        env,
        lcd_exec=(
            f"{root}/bin/truepanel run"
        ),
    )

    results = check_service_units(
        root,
        units,
        env,
    )

    assert [
        item["status"]
        for item in results
    ] == [
        PASS,
        PASS,
        PASS,
    ]


def test_service_units_accept_postinit_python_launcher(
    tmp_path,
):
    root = tmp_path / "install"
    units = tmp_path / "systemd"
    env = tmp_path / "default"
    root.mkdir()

    _write_valid_service_scaffolding(
        root,
        units,
        env,
        lcd_exec=(
            f"{root}/.venv/bin/python "
            f"{root}/truepanel.py run"
        ),
    )

    results = check_service_units(
        root,
        units,
        env,
    )

    assert [
        item["status"]
        for item in results
    ] == [
        PASS,
        PASS,
        PASS,
    ]


def test_service_units_reject_unrelated_lcd_launcher(
    tmp_path,
):
    root = tmp_path / "install"
    units = tmp_path / "systemd"
    env = tmp_path / "default"
    root.mkdir()

    _write_valid_service_scaffolding(
        root,
        units,
        env,
        lcd_exec=(
            "/tmp/OtherTruePanel/bin/truepanel run"
        ),
    )

    results = check_service_units(
        root,
        units,
        env,
    )

    assert results[0]["status"] == FAIL
    assert results[1]["status"] == PASS
    assert results[2]["status"] == PASS


def test_service_state_passes_for_active_service():
    result = check_service_state(
        "truepanel.service",
        runner=lambda *args, **kwargs: (
            CommandResult(
                returncode=0,
                stdout="active\n",
            )
        ),
    )

    assert result["status"] == PASS
    assert result["detail"] == "active"


def test_service_state_fails_for_inactive_service():
    result = check_service_state(
        "truepanel.service",
        runner=lambda *args, **kwargs: (
            CommandResult(
                returncode=3,
                stdout="inactive\n",
            )
        ),
    )

    assert result["status"] == FAIL
    assert result["detail"] == "inactive"


def test_expected_inactive_service_passes_only_when_inactive():
    result = check_service_inactive(
        "truepanel-host-agent.service",
        runner=lambda *args, **kwargs: (
            CommandResult(
                returncode=3,
                stdout="inactive\n",
            )
        ),
    )

    assert result["status"] == PASS
    assert result["detail"] == "inactive"


def test_expected_inactive_service_fails_when_active():
    result = check_service_inactive(
        "truepanel-host-agent.service",
        runner=lambda *args, **kwargs: (
            CommandResult(
                returncode=0,
                stdout="active\n",
            )
        ),
    )

    assert result["status"] == FAIL
    assert "Expected inactive" in result["detail"]
    assert "active" in result["detail"]


def test_verify_checks_standalone_host_agent_is_dormant():
    source = Path(
        "truepanel/verify/checks.py"
    ).read_text(encoding="utf-8")

    start = source.index("def run_checks(")
    end = source.index("\ndef ", start + 1)
    block = source[start:end]

    assert "check_service_inactive(" in block
    assert '"truepanel-host-agent.service"' in block


def test_postinit_accepts_enabled_startup_task(
    tmp_path,
):
    startup = (
        tmp_path / "start-truepanel.sh"
    )

    result = check_postinit(
        tmp_path,
        runner=lambda *args, **kwargs: (
            CommandResult(
                stdout=json.dumps(
                    [
                        {
                            "id": 8,
                            "type": "SCRIPT",
                            "script": str(startup),
                            "when": "POSTINIT",
                            "enabled": True,
                        }
                    ]
                )
            )
        ),
    )

    assert result["status"] == PASS
    assert result["detail"] == "Task 8"


def test_postinit_rejects_disabled_task(
    tmp_path,
):
    startup = (
        tmp_path / "start-truepanel.sh"
    )

    result = check_postinit(
        tmp_path,
        runner=lambda *args, **kwargs: (
            CommandResult(
                stdout=json.dumps(
                    [
                        {
                            "id": 8,
                            "type": "SCRIPT",
                            "script": str(startup),
                            "when": "POSTINIT",
                            "enabled": False,
                        }
                    ]
                )
            )
        ),
    )

    assert result["status"] == FAIL


def test_lcd_transport_requires_complete_health():
    result = check_lcd_transport(
        {
            "lcd": {
                "reader": {
                    "healthy": True,
                    "connected": True,
                    "thread_alive": True,
                    "dispatcher_alive": True,
                    "port": "/dev/ttyS1",
                    "speed": 1200,
                    "reader_errors": 0,
                }
            }
        }
    )

    assert result["status"] == PASS
    assert "port=/dev/ttyS1" in result["detail"]


def test_run_verify_returns_failure(
    tmp_path,
    monkeypatch,
):
    create_installation(tmp_path)

    units = tmp_path / "systemd"
    env = tmp_path / "default"
    units.mkdir()
    env.mkdir()

    monkeypatch.setenv(
        "TRUEPANEL_VERIFY_SYSTEMD_DIR",
        str(units),
    )
    monkeypatch.setenv(
        "TRUEPANEL_VERIFY_ENV_DIR",
        str(env),
    )

    code = run_verify(
        root=tmp_path,
        runner=lambda *args, **kwargs: (
            CommandResult(
                returncode=3,
                stdout="inactive\n",
            )
        ),
        opener=lambda *args, **kwargs: Response(
            {
                "lcd": {
                    "reader": {
                        "healthy": False,
                    }
                }
            }
        ),
    )

    assert code == 1


def test_project_root_honors_shared_environment_root(
    tmp_path,
    monkeypatch,
):
    from truepanel.verify.checks import (
        project_root,
    )

    monkeypatch.delenv(
        "TRUEPANEL_VERIFY_ROOT",
        raising=False,
    )
    monkeypatch.setenv(
        "TRUEPANEL_ROOT",
        str(tmp_path),
    )

    assert project_root() == tmp_path.resolve()


def test_project_root_honors_environment_override(
    tmp_path,
    monkeypatch,
):
    from truepanel.verify.checks import (
        project_root,
    )

    monkeypatch.setenv(
        "TRUEPANEL_VERIFY_ROOT",
        str(tmp_path),
    )

    assert project_root() == tmp_path.resolve()
