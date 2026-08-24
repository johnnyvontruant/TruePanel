import io
import json
from types import SimpleNamespace

from truepanel.lifeline import LifelineSessionStore
from truepanel.web.server import MissionControlRequestHandler


def fault_payload():
    return {
        "storage": {
            "pools": [{"name": "HDDs", "health": "DEGRADED"}],
            "zfs_activity": {"resilver_running": False},
        },
        "operator_guidance": [
            {
                "code": "storage.disk_faulted",
                "runtime": {
                    "evidence": {
                        "pool": "HDDs",
                        "pool_state": "DEGRADED",
                        "vdev": "raidz1-0",
                        "vdev_topology": "RAIDZ1",
                        "remaining_redundancy": 0,
                        "device": "sdc",
                        "bay": 3,
                        "zfs_state": "FAULTED",
                        "capacity_bytes": 8_000_000_000_000,
                        "resilver_state": {"resilver_running": False},
                    }
                },
            }
        ],
    }


class IdentifyService:
    def __init__(self):
        self.calls = []

    def identify(self, bay):
        self.calls.append(bay)
        return {
            "bay": bay,
            "identify": True,
            "duration_seconds": 15.0,
            "storage_mutation": False,
            "hardware_action": "identify_led",
        }


def handler(tmp_path, *, model="TVS-671", body=None, intent=True):
    store = LifelineSessionStore(path=tmp_path / "lifeline.json")
    observed = store.observe(fault_payload())
    session_id = observed["lifeline"]["sessions"][0]["id"]
    payload = body or {
        "session_id": session_id,
        "confirmation": "IDENTIFY_FAILED_BAY",
    }
    raw = json.dumps(payload).encode("utf-8")
    identify = IdentifyService()
    snapshot_service = SimpleNamespace(
        lifeline_store=store,
        lifeline_service_profile=SimpleNamespace(selected_model=model),
    )

    request = object.__new__(MissionControlRequestHandler)
    request.server = SimpleNamespace(
        snapshot_service=snapshot_service,
        lifeline_identify_service=identify,
    )
    request.headers = {"Content-Length": str(len(raw))}
    if intent:
        request.headers["X-TruePanel-Intent"] = "lifeline-identify-bay"
    request.rfile = io.BytesIO(raw)
    captured = []
    request._json = lambda data, **kwargs: captured.append((data, kwargs))
    return request, captured, identify, session_id


def test_identify_uses_session_bay_not_browser_supplied_bay(tmp_path):
    request, captured, identify, _session_id = handler(tmp_path)

    request._lifeline_identify(None)

    assert identify.calls == [3]
    payload, kwargs = captured[0]
    assert kwargs == {}
    assert payload["ok"] is True
    assert payload["storage_mutation"] is False
    assert payload["action"]["bay"] == 3


def test_identify_rejects_any_browser_supplied_bay(tmp_path):
    request, captured, identify, session_id = handler(
        tmp_path,
        body={
            "session_id": session_id if False else "placeholder",
            "confirmation": "IDENTIFY_FAILED_BAY",
            "bay": 4,
        },
    )
    # Replace the placeholder with the actual session while retaining the
    # forbidden bay field.
    actual = request.server.snapshot_service.lifeline_store.snapshot()["sessions"][0]["id"]
    raw = json.dumps(
        {
            "session_id": actual,
            "confirmation": "IDENTIFY_FAILED_BAY",
            "bay": 4,
        }
    ).encode("utf-8")
    request.headers["Content-Length"] = str(len(raw))
    request.rfile = io.BytesIO(raw)

    request._lifeline_identify(None)

    assert identify.calls == []
    assert captured[0][0]["error"] == "lifeline_identify_rejected"


def test_identify_requires_intent_header(tmp_path):
    request, captured, identify, _session_id = handler(tmp_path, intent=False)

    request._lifeline_identify(None)

    assert identify.calls == []
    assert captured[0][0]["error"] == "lifeline_identify_intent_required"


def test_identify_is_locked_for_unverified_neighboring_model(tmp_path):
    request, captured, identify, _session_id = handler(
        tmp_path,
        model="TVS-871",
    )

    request._lifeline_identify(None)

    assert identify.calls == []
    assert captured[0][0]["error"] == "lifeline_identify_profile_not_verified"


def test_identify_requires_exact_confirmation_token(tmp_path):
    request, captured, identify, session_id = handler(
        tmp_path,
        body={
            "session_id": "placeholder",
            "confirmation": "IDENTIFY_SOMETHING",
        },
    )
    actual = request.server.snapshot_service.lifeline_store.snapshot()["sessions"][0]["id"]
    raw = json.dumps(
        {
            "session_id": actual,
            "confirmation": "IDENTIFY_SOMETHING",
        }
    ).encode("utf-8")
    request.headers["Content-Length"] = str(len(raw))
    request.rfile = io.BytesIO(raw)

    request._lifeline_identify(None)

    assert identify.calls == []
    assert captured[0][0]["error"] == "lifeline_identify_rejected"
