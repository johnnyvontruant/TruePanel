"""Evidence qualifier cannot infer authority from file existence alone."""
from truepanel.loadmaster.evidence import qualified_preflight


def test_qualifier_defaults_to_deny(tmp_path):
    result = qualified_preflight(
        registry_path=tmp_path / "registry.json",
        backlog_path=tmp_path / "backlog.json",
        manifest_path=tmp_path / "manifest.json",
        status={"available": True, "state": "READY"},
    )
    assert result is None


def test_commissioned_callback_cannot_bypass_missing_evidence(tmp_path):
    result = qualified_preflight(
        registry_path=tmp_path / "registry.json",
        backlog_path=tmp_path / "backlog.json",
        manifest_path=tmp_path / "manifest.json",
        status={"available": True, "age": 0, "state": "READY",
                "plan": {"state": "READY", "needs_confirmation": False,
                         "digest": "a" * 64,
                         "summary": {"to_usb_files": 1, "to_usb_bytes": 100},
                         "preview": [{"op": "TO_USB", "path": "movie.mkv"}]},
                "drive": {"name": "Untitled", "uuid": "6ADA-80D5",
                          "serial": "2532EA8D421A"}},
        baseline_verified=lambda identity, uuid: True,
    )
    assert result is None


def test_stale_plan_rejected_before_evidence_io(tmp_path):
    result = qualified_preflight(
        registry_path=tmp_path / "registry.json",
        backlog_path=tmp_path / "backlog.json",
        manifest_path=tmp_path / "manifest.json",
        status={"available": True, "age": 100, "state": "READY"},
        baseline_verified=lambda identity, uuid: True,
    )
    assert result is None
