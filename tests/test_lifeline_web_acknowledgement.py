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


def handler(tmp_path, *, intent=True, body=None):
    store = LifelineSessionStore(path=tmp_path / "lifeline.json")
    observed = store.observe(fault_payload())
    session_id = observed["lifeline"]["sessions"][0]["id"]
    payload = body or {
        "session_id": session_id,
        "acknowledgement": "backup_state",
        "value": True,
        "confirmation": "ACKNOWLEDGE_BACKUP_STATE",
    }
    raw = json.dumps(payload).encode("utf-8")

    request = object.__new__(MissionControlRequestHandler)
    request.server = SimpleNamespace(
        snapshot_service=SimpleNamespace(lifeline_store=store)
    )
    request.headers = {
        "Content-Length": str(len(raw)),
    }
    if intent:
        request.headers["X-TruePanel-Intent"] = "lifeline-backup-ack"
    request.rfile = io.BytesIO(raw)
    captured = []
    request._json = lambda data, **kwargs: captured.append((data, kwargs))
    return request, captured, store, session_id


def test_acknowledgement_requires_custom_same_origin_intent(tmp_path):
    request, captured, store, session_id = handler(tmp_path, intent=False)

    request._lifeline_acknowledge(None)

    assert captured[0][0]["error"] == "lifeline_intent_required"
    session = next(
        item for item in store.snapshot()["sessions"] if item["id"] == session_id
    )
    assert session["context"]["acknowledgements"]["backup_state"] is False


def test_valid_acknowledgement_changes_only_lifeline_metadata(tmp_path):
    request, captured, store, session_id = handler(tmp_path)

    request._lifeline_acknowledge(None)

    payload, kwargs = captured[0]
    assert kwargs == {}
    assert payload["ok"] is True
    assert payload["hardware_mutation"] is False
    assert payload["session"]["id"] == session_id
    assert (
        store.snapshot()["sessions"][0]["context"]["acknowledgements"][
            "backup_state"
        ]
        is True
    )


def test_acknowledgement_rejects_storage_action_names(tmp_path):
    request, captured, _store, _session_id = handler(
        tmp_path,
        body={
            "session_id": "drive:HDDs:raidz1-0:sdc",
            "acknowledgement": "replace_disk",
            "value": True,
            "confirmation": "ACKNOWLEDGE_BACKUP_STATE",
        },
    )

    request._lifeline_acknowledge(None)

    assert captured[0][0]["error"] == "lifeline_acknowledgement_rejected"
