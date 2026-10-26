from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from urllib.request import urlopen

from test_web_lcd_control import (
    FakeFanCommandClient,
    FakeLCDCommandClient,
    FakeSnapshotService,
    post_json,
)

from truepanel.loadmaster.link import (
    LinkError,
    plan_path_for,
    publish_plan,
    publish_status,
)
from truepanel.web.server import MissionControlServer


@contextmanager
def server(sender=None, status_path=None):
    srv = MissionControlServer(
        ("127.0.0.1", 0),
        snapshot_service=FakeSnapshotService(),
        fan_command_client=FakeFanCommandClient(),
        lcd_command_client=FakeLCDCommandClient(),
    )
    srv.loadmaster_sender = sender
    srv.loadmaster_status_path = status_path
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = srv.server_address
        yield f"http://{host}:{port}"
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)


def test_status_endpoint(tmp_path):
    path = tmp_path / "s.json"
    publish_status(path, {"state": "READY", "drive": {"name": "TV A-M"}})
    with server(status_path=path) as base, urlopen(base + "/api/v1/loadmaster") as r:
        body = json.load(r)
    assert body["state"] == "READY" and body["available"] is True


def test_plan_endpoint_serves_the_whole_plan(tmp_path):
    status = tmp_path / "loadmaster-status.json"
    actions = [
        {"op": "to_usb", "path": f"Show/S01E{i:02}.mkv", "size": i} for i in range(60)
    ]
    publish_plan(
        plan_path_for(status), {"digest": "d" * 64, "actions": actions, "notices": []}
    )
    with (
        server(status_path=status) as base,
        urlopen(base + "/api/v1/loadmaster/plan") as r,
    ):
        body = json.load(r)
    assert body["available"] is True
    assert body["plan"]["digest"] == "d" * 64 and len(body["plan"]["actions"]) == 60


def test_plan_endpoint_without_a_plan(tmp_path):
    with (
        server(status_path=tmp_path / "s.json") as base,
        urlopen(base + "/api/v1/loadmaster/plan") as r,
    ):
        assert json.load(r) == {"available": False, "plan": None}


def test_command_is_relayed_as_web_even_if_body_claims_lcd():
    seen = []

    def sender(request):
        seen.append(request)
        return {"ok": True, "status": "started", "message": "ok"}

    body = {"action": "start", "digest": "a" * 64, "confirm": True, "source": "lcd"}
    with server(sender) as base:
        code, answer = post_json(base + "/api/v1/loadmaster/command", body)
    assert code == 200 and answer["status"] == "started"
    assert seen == [
        {"action": "start", "source": "web", "digest": "a" * 64, "confirm": True}
    ]


def test_unconfirmed_start_and_bad_actions_are_rejected_before_relay():
    seen = []
    with server(lambda r: seen.append(r) or {"ok": True}) as base:
        url = base + "/api/v1/loadmaster/command"
        assert post_json(url, {"action": "start", "digest": "a" * 64})[0] == 409
        assert post_json(url, {"action": "format"})[0] == 400
        assert post_json(url, {"action": "eject", "extra": 1})[0] == 400
    assert seen == []


def test_refusal_and_unreachable_service():
    with server(lambda r: {"ok": False, "status": "not_ready", "message": "x"}) as base:
        assert (
            post_json(base + "/api/v1/loadmaster/command", {"action": "eject"})[0]
            == 409
        )

    def down(request):
        raise LinkError("socket missing")

    with server(down) as base:
        code, answer = post_json(
            base + "/api/v1/loadmaster/command", {"action": "eject"}
        )
    assert code == 503 and answer["status"] == "unavailable"


def test_relayed_request_is_accepted_by_the_service_side_validator():
    """What Mission Control forwards must pass the service's own validation."""

    from truepanel.loadmaster.link import validate

    seen = []
    with server(lambda r: seen.append(r) or {"ok": True}) as base:
        post_json(
            base + "/api/v1/loadmaster/command",
            {"action": "start", "digest": "b" * 64, "confirm": True},
        )
    clean, error = validate(seen[0])
    assert error is None and clean == seen[0]
