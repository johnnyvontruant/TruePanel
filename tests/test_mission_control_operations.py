import io
import subprocess
from contextlib import redirect_stdout
from pathlib import Path

from truepanel.web.operations import (
    MissionControlStatus,
    environment_settings,
    get_status,
    print_status,
    read_environment,
)


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return b'{"status":"ok"}'


def test_environment_defaults_are_safe():
    host, port, writes, url = environment_settings({})

    assert host == "127.0.0.1"
    assert port == 8787
    assert writes is False
    assert url == "http://127.0.0.1:8787"


def test_lan_binding_uses_operator_friendly_url():
    host, port, writes, url = environment_settings(
        {
            "TRUEPANEL_MC_HOST": "0.0.0.0",
            "TRUEPANEL_MC_PORT": "8787",
            "TRUEPANEL_MC_ALLOW_CONFIG_WRITES": "false",
        }
    )

    assert host == "0.0.0.0"
    assert port == 8787
    assert writes is False
    assert url == "http://<BattleStation-IP>:8787"


def test_environment_reader_ignores_comments(tmp_path):
    path = tmp_path / "mission-control.env"
    path.write_text(
        "\n".join(
            [
                "# comment",
                "TRUEPANEL_MC_HOST=0.0.0.0",
                "TRUEPANEL_MC_PORT=9000",
            ]
        ),
        encoding="utf-8",
    )

    values = read_environment(path)

    assert values["TRUEPANEL_MC_HOST"] == "0.0.0.0"
    assert values["TRUEPANEL_MC_PORT"] == "9000"


def test_status_combines_systemd_and_health(tmp_path):
    env_path = tmp_path / "mission-control.env"
    env_path.write_text(
        "\n".join(
            [
                "TRUEPANEL_MC_HOST=0.0.0.0",
                "TRUEPANEL_MC_PORT=8787",
                "TRUEPANEL_MC_ALLOW_CONFIG_WRITES=false",
            ]
        ),
        encoding="utf-8",
    )

    def runner(*args, **kwargs):
        return subprocess.CompletedProcess(
            args[0],
            0,
            stdout=(
                "LoadState=loaded\n"
                "UnitFileState=enabled\n"
                "ActiveState=active\n"
                "SubState=running\n"
            ),
            stderr="",
        )

    status = get_status(
        env_path=env_path,
        runner=runner,
        opener=lambda *args, **kwargs: FakeResponse(),
    )

    assert status.loaded == "loaded"
    assert status.enabled == "enabled"
    assert status.active == "active"
    assert status.health == "healthy"
    assert status.writes_enabled is False


def test_status_output_is_operator_friendly():
    status = MissionControlStatus(
        loaded="loaded",
        enabled="enabled",
        active="active",
        substate="running",
        host="0.0.0.0",
        port=8787,
        writes_enabled=False,
        url="http://<BattleStation-IP>:8787",
        health="healthy",
    )

    output = io.StringIO()

    with redirect_stdout(output):
        print_status(status)

    rendered = output.getvalue()

    assert "TruePanel Mission Control" in rendered
    assert "active / running" in rendered
    assert "http://<BattleStation-IP>:8787" in rendered
    assert "read only" in rendered
