"""Validate privileged host-only Loadmaster v2 start boundary."""
from dataclasses import replace

from truepanel.loadmaster.config import Drive, Settings
from truepanel.loadmaster.service import LoadmasterService
from truepanel.loadmaster.state import StateStore


def service(tmp_path, commissioned=False):
    settings = Settings(
        drives=(Drive("Untitled", tmp_path / "nas", "data"),),
        state_dir=tmp_path / "state",
        status_path=tmp_path / "status.json",
        command_socket=tmp_path / "commands.sock",
        remote_start=False,
        extra={"physical_bridge_enabled": commissioned},
    )
    subject = LoadmasterService(settings, store=StateStore(settings.state_dir))
    subject.state = "READY"
    subject.plan = {
        "digest": "a" * 64,
        "needs_confirmation": False,
        "summary": {
            "to_usb_files": 1,
            "to_usb_bytes": 100,
            "to_nas_files": 0,
            "delete_usb_files": 0,
            "retire_nas_files": 0,
            "conflicts": 0,
        },
    }
    subject.docked = object()
    return subject


def test_host_start_disabled_even_when_authenticated(tmp_path):
    subject = service(tmp_path)
    result = subject.handle({
        "action": "start", "source": "host", "digest": "a" * 64,
        "_host_authenticated": True,
    })
    assert result["status"] == "bridge_disabled"
    assert subject.state == "READY"


def test_host_start_refuses_untrusted_origin(tmp_path):
    subject = service(tmp_path, commissioned=True)
    result = subject.handle({
        "action": "start", "source": "host", "digest": "a" * 64,
    })
    assert result["status"] == "unauthorized"
    assert subject.state == "READY"


def test_host_start_refuses_ingest_and_deletions(tmp_path):
    for field in ("to_nas_files", "delete_usb_files", "retire_nas_files", "conflicts"):
        subject = service(tmp_path, commissioned=True)
        subject.plan["summary"][field] = 1
        result = subject.handle({
            "action": "start", "source": "host", "digest": "a" * 64,
            "_host_authenticated": True,
        })
        assert result["status"] == "unsafe_plan"
        assert subject.state == "READY"


def test_host_start_rejects_stale_digest(tmp_path):
    subject = service(tmp_path, commissioned=True)
    result = subject.handle({
        "action": "start", "source": "host", "digest": "b" * 64,
        "_host_authenticated": True,
    })
    assert result["status"] == "plan_changed"
    assert subject.state == "READY"
