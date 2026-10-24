"""Validate privileged host-only Loadmaster v2 start boundary."""
from types import SimpleNamespace

from truepanel.loadmaster.host_token import TokenVerifier, issue

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
    subject.docked = SimpleNamespace(device=SimpleNamespace(uuid="6ADA-80D5", serial="2532EA8D421A"))
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
    key = b"test-only-key-material" * 2
    subject.settings.extra["physical_token_key"] = "/test/key"
    subject._host_token_verifier = TokenVerifier(key)
    result = subject.handle({
        "action": "start", "source": "host", "digest": "b" * 64,
        "_host_authenticated": True,
        "token": issue(key, "b" * 64, "6ADA-80D5", "2532EA8D421A"),
    })
    assert result["status"] == "plan_changed"
    assert subject.state == "READY"


def test_host_start_rejects_missing_token_before_plan_check(tmp_path):
    subject = service(tmp_path, commissioned=True)
    result = subject.handle({
        "action": "start", "source": "host", "digest": "b" * 64,
        "_host_authenticated": True,
    })
    assert result["status"] == "unauthorized"
    assert subject.state == "READY"


def test_host_start_rejects_changed_cartridge_before_spending_token(tmp_path):
    subject = service(tmp_path, commissioned=True)
    key = b"test-only-key-material" * 2
    subject.settings.extra["physical_token_key"] = "/test/key"
    subject._host_token_verifier = TokenVerifier(key)
    subject.dock.scan = lambda: []
    result = subject.handle({
        "action": "start", "source": "host", "digest": "a" * 64,
        "_host_authenticated": True,
        "token": issue(key, "a" * 64, "6ADA-80D5", "2532EA8D421A"),
    })
    assert result["status"] == "drive_changed"
    assert subject.state == "READY"
    assert not subject._host_token_verifier.used
