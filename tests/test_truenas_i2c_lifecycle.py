import json
from pathlib import Path

import pytest

from truepanel.lifecycle import truenas_i2c


def task(**overrides):
    result = {
        "id": 17,
        "type": "COMMAND",
        "command": truenas_i2c.TASK_COMMAND,
        "script": "",
        "when": truenas_i2c.TASK_WHEN,
        "enabled": True,
        "timeout": truenas_i2c.TASK_TIMEOUT,
        "comment": truenas_i2c.TASK_COMMENT,
    }
    result.update(overrides)
    return result


class FakeMiddleware:
    def __init__(self, tasks=None):
        self.tasks = list(tasks or [])
        self.calls = []
        self.next_id = 100

    def __call__(self, method, *arguments):
        self.calls.append((method, arguments))
        if method == "initshutdownscript.query":
            return [dict(item) for item in self.tasks]
        if method == "initshutdownscript.create":
            created = {"id": self.next_id, **arguments[0]}
            self.tasks.append(created)
            self.next_id += 1
            return dict(created)
        if method == "initshutdownscript.update":
            task_id, payload = arguments
            for index, item in enumerate(self.tasks):
                if item["id"] == task_id:
                    self.tasks[index] = {"id": task_id, **payload}
                    return dict(self.tasks[index])
        if method == "initshutdownscript.delete":
            task_id = arguments[0]
            self.tasks = [item for item in self.tasks if item["id"] != task_id]
            return True
        raise AssertionError(method)


@pytest.fixture
def loaded_module(monkeypatch, tmp_path):
    module_path = tmp_path / "i2c_dev"
    module_path.mkdir()
    monkeypatch.setenv("TRUEPANEL_I2C_MODULE_PATH", str(module_path))
    monkeypatch.setattr(
        truenas_i2c,
        "_tool",
        lambda name, override: f"/fake/{name}",
    )
    commands = []

    def run(command):
        commands.append(command)
        return type("Result", (), {"stdout": "", "stderr": ""})()

    monkeypatch.setattr(truenas_i2c, "_run", run)
    return commands


def test_ensure_creates_owned_postinit_task(monkeypatch, loaded_module):
    middleware = FakeMiddleware()
    monkeypatch.setattr(truenas_i2c, "_midclt_call", middleware)

    assert truenas_i2c.ensure_persistence() == "created"
    assert loaded_module == [["/fake/modprobe", "i2c-dev"]]
    assert middleware.tasks == [
        {"id": 100, **truenas_i2c._desired_task()}
    ]


def test_ensure_is_idempotent_for_owned_task(monkeypatch, loaded_module):
    middleware = FakeMiddleware([task()])
    monkeypatch.setattr(truenas_i2c, "_midclt_call", middleware)

    assert truenas_i2c.ensure_persistence() == "preserved"
    assert [call[0] for call in middleware.calls] == [
        "initshutdownscript.query",
        "initshutdownscript.query",
    ]


def test_ensure_updates_drifted_owned_task(monkeypatch, loaded_module):
    middleware = FakeMiddleware([task(enabled=False, when="PREINIT")])
    monkeypatch.setattr(truenas_i2c, "_midclt_call", middleware)

    assert truenas_i2c.ensure_persistence() == "updated"
    assert middleware.tasks == [
        {"id": 17, **truenas_i2c._desired_task()}
    ]


def test_ensure_preserves_equivalent_operator_task(monkeypatch, loaded_module):
    operator_task = task(id=9, comment="Operator-owned SMBus preload")
    middleware = FakeMiddleware([operator_task])
    monkeypatch.setattr(truenas_i2c, "_midclt_call", middleware)

    assert truenas_i2c.ensure_persistence() == "external"
    assert middleware.tasks == [operator_task]
    assert all(
        call[0] not in {
            "initshutdownscript.create",
            "initshutdownscript.update",
        }
        for call in middleware.calls
    )


def test_ensure_fails_closed_on_duplicate_owned_tasks(
    monkeypatch,
    loaded_module,
):
    middleware = FakeMiddleware([task(id=1), task(id=2)])
    monkeypatch.setattr(truenas_i2c, "_midclt_call", middleware)

    with pytest.raises(truenas_i2c.LifecycleError, match="Multiple"):
        truenas_i2c.ensure_persistence()


def test_remove_deletes_only_owned_tasks(monkeypatch):
    operator_task = task(id=9, comment="Operator-owned SMBus preload")
    middleware = FakeMiddleware([task(id=17), operator_task])
    monkeypatch.setattr(truenas_i2c, "_midclt_call", middleware)

    assert truenas_i2c.remove_persistence() == 1
    assert middleware.tasks == [operator_task]


def test_midclt_serializes_api_arguments(monkeypatch):
    monkeypatch.setattr(
        truenas_i2c,
        "_tool",
        lambda name, override: "/usr/bin/midclt",
    )
    captured = []

    def run(command):
        captured.append(command)
        return type("Result", (), {"stdout": "[]", "stderr": ""})()

    monkeypatch.setattr(truenas_i2c, "_run", run)
    payload = truenas_i2c._desired_task()

    truenas_i2c._midclt_call("initshutdownscript.update", 17, payload)

    assert captured == [
        [
            "/usr/bin/midclt",
            "call",
            "initshutdownscript.update",
            "17",
            json.dumps(payload, separators=(",", ":")),
        ]
    ]


def test_lifecycle_source_avoids_modules_load_files():
    root = Path(__file__).resolve().parents[1]
    for name in (
        "install.sh",
        "uninstall.sh",
    ):
        assert "/etc/modules-load.d" not in (root / name).read_text(
            encoding="utf-8"
        )


def test_install_and_uninstall_disclose_owned_postinit_lifecycle():
    root = Path(__file__).resolve().parents[1]
    installer = (root / "install.sh").read_text(encoding="utf-8")
    uninstaller = (root / "uninstall.sh").read_text(encoding="utf-8")

    assert 'python3 "$I2C_LIFECYCLE_HELPER" ensure' in installer
    assert 'python3 "$I2C_LIFECYCLE_HELPER" remove' in uninstaller
    assert "Persist i2c-dev with a TrueNAS-managed POSTINIT task" in installer
    assert "TruePanel-managed i2c-dev POSTINIT task" in uninstaller
