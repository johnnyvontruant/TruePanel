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

from truepanel.cargo.loadmaster_link import (
    START_CONFIRMATION,
    LoadmasterLinkError,
    publish_status,
)
from truepanel.web.server import MissionControlServer


class FakeLoadmasterClient:
    def __init__(self, response=None, error=None):
        self.calls = []
        self.response = response or {"ok": True, "status": "ejected", "message": "ok"}
        self.error = error

    def request(self, action, *, source, **fields):
        self.calls.append((action, source, fields))
        if self.error is not None:
            raise self.error
        return dict(self.response)


@contextmanager
def running_server(client, status_path=None):
    server = MissionControlServer(
        ("127.0.0.1", 0),
        snapshot_service=FakeSnapshotService(),
        fan_command_client=FakeFanCommandClient(),
        lcd_command_client=FakeLCDCommandClient(),
    )
    server.loadmaster_command_client = client
    if status_path is not None:
        server.loadmaster_status_path = status_path
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_status_endpoint_serves_published_status(tmp_path):
    path = tmp_path / "loadmaster-status.json"
    publish_status({"state": "READY", "cartridge": {"label": "TV A-M"}}, path)

    with running_server(FakeLoadmasterClient(), path) as base:
        with urlopen(base + "/api/v1/loadmaster", timeout=5) as response:
            payload = json.load(response)

    assert payload["state"] == "READY"
    assert payload["available"] is True


def test_status_endpoint_without_controller_is_unavailable(tmp_path):
    with running_server(FakeLoadmasterClient(), tmp_path / "none.json") as base:
        with urlopen(base + "/api/v1/loadmaster", timeout=5) as response:
            payload = json.load(response)

    assert payload["state"] == "UNAVAILABLE"


def test_start_is_relayed_with_digest_and_confirmation():
    client = FakeLoadmasterClient({"ok": True, "status": "started", "message": "ok"})
    body = {
        "action": "start",
        "plan_digest": "a" * 64,
        "confirmation": START_CONFIRMATION,
    }

    with running_server(client) as base:
        status, payload = post_json(base + "/api/v1/loadmaster/command", body)

    assert status == 200
    assert payload["status"] == "started"
    assert client.calls == [
        (
            "start",
            "web",
            {"plan_digest": "a" * 64, "confirmation": START_CONFIRMATION},
        )
    ]


def test_refusals_map_to_conflict():
    client = FakeLoadmasterClient(
        {"ok": False, "status": "remote_disabled", "message": "press Copy"}
    )

    with running_server(client) as base:
        status, payload = post_json(
            base + "/api/v1/loadmaster/command", {"action": "start"}
        )

    assert status == 409
    assert payload["status"] == "remote_disabled"


def test_unknown_fields_are_rejected_before_relay():
    client = FakeLoadmasterClient()

    with running_server(client) as base:
        status, _payload = post_json(
            base + "/api/v1/loadmaster/command",
            {"action": "eject", "source": "lcd"},
        )

    assert status == 400
    assert client.calls == []


def test_unreachable_controller_is_service_unavailable():
    client = FakeLoadmasterClient(error=LoadmasterLinkError("no socket"))

    with running_server(client) as base:
        status, payload = post_json(
            base + "/api/v1/loadmaster/command", {"action": "eject"}
        )

    assert status == 503
    assert payload["error"] == "loadmaster_unavailable"
