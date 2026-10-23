from __future__ import annotations

import json
import tempfile
from dataclasses import replace
from pathlib import Path

from test_loadmaster_controller import docked_for, rig

from truepanel.cargo.dock import BlockDevice, DockScan
from truepanel.cargo.loadmaster_link import (
    START_CONFIRMATION,
    LoadmasterCommandClient,
    LoadmasterCommandProcessor,
    LoadmasterCommandServer,
    publish_status,
    read_status,
)


class FakeController:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def request_start(self, *, plan_digest, source):
        self.calls.append(("start", plan_digest, source))
        return {"ok": True, "status": "started", "message": "ok"}

    def request_eject(self, *, source):
        self.calls.append(("eject", source))
        return {"ok": True, "status": "ejected", "message": "ok"}

    def request_refresh(self, *, source):
        self.calls.append(("refresh", source))
        return {"ok": True, "status": "refreshed", "message": "READY"}


DIGEST = "a" * 64


def test_status_round_trip_and_staleness(tmp_path):
    path = tmp_path / "status.json"
    publish_status({"state": "READY"}, path)

    fresh = read_status(path)
    assert fresh["state"] == "READY"
    assert fresh["available"] is True

    document = json.loads(path.read_text())
    document["published_at"] -= 600
    path.write_text(json.dumps(document))
    stale = read_status(path)
    assert stale["stale"] is True
    assert stale["available"] is False


def test_missing_status_is_unavailable(tmp_path):
    status = read_status(tmp_path / "absent.json")
    assert status["state"] == "UNAVAILABLE"
    assert status["available"] is False


def test_processor_requires_digest_and_confirmation_for_start():
    controller = FakeController()
    processor = LoadmasterCommandProcessor(controller)

    assert processor.process({"action": "start", "source": "web"})["status"] == (
        "invalid_request"
    )
    refused = processor.process(
        {"action": "start", "source": "web", "plan_digest": DIGEST}
    )
    assert refused["status"] == "confirmation_required"
    assert controller.calls == []

    accepted = processor.process(
        {
            "action": "start",
            "source": "web",
            "plan_digest": DIGEST,
            "confirmation": START_CONFIRMATION,
        }
    )
    assert accepted["ok"] is True
    assert controller.calls == [("start", DIGEST, "web")]


def test_processor_rejects_unknown_actions_sources_and_fields():
    processor = LoadmasterCommandProcessor(FakeController())

    assert processor.process({"action": "delete", "source": "web"})["status"] == (
        "unknown_action"
    )
    assert processor.process({"action": "eject", "source": "gpio"})["status"] == (
        "invalid_source"
    )
    assert processor.process({"action": "eject", "source": "web", "x": 1})[
        "status"
    ] == ("invalid_request")


def test_socket_round_trip():
    controller = FakeController()
    directory = Path(tempfile.mkdtemp(prefix="lm-", dir="/tmp"))
    server = LoadmasterCommandServer(
        LoadmasterCommandProcessor(controller), directory / "lm.sock"
    )
    server.start()
    try:
        client = LoadmasterCommandClient(directory / "lm.sock", timeout=5)
        reply = client.request("eject", source="lcd")
    finally:
        server.stop()

    assert reply["status"] == "ejected"
    assert controller.calls == [("eject", "lcd")]


# --------------------------------------------------------- controller commands


def _ready(tmp_path, *, remote: bool):
    bay, controller, dock, button, clock = rig(tmp_path)
    controller.settings = replace(controller.settings, remote_confirmation=remote)
    published: list[dict] = []
    controller.status_publisher = published.append
    dock.present = [docked_for(bay)]
    controller.tick()
    assert controller.snapshot()["state"] == "READY"
    return bay, controller, dock, published


def test_remote_start_refused_unless_enabled(tmp_path):
    _bay, controller, dock, _published = _ready(tmp_path, remote=False)
    digest = controller.snapshot()["plan"]["digest"]

    reply = controller.request_start(plan_digest=digest, source="web")

    assert reply["status"] == "remote_disabled"
    assert "rw" not in dock.calls


def test_remote_start_runs_the_shown_plan(tmp_path):
    bay, controller, dock, published = _ready(tmp_path, remote=True)

    stale = controller.request_start(plan_digest="b" * 64, source="web")
    assert stale["status"] == "plan_changed"

    digest = controller.snapshot()["plan"]["digest"]
    reply = controller.request_start(plan_digest=digest, source="web")

    assert reply["ok"] is True
    assert controller.snapshot()["state"] == "COMPLETE"
    assert (bay.usb_root / "Inception (2010)/Inception.mkv").exists()
    states = [item["state"] for item in published]
    assert "EXECUTING" in states and states[-1] == "COMPLETE"


def test_eject_unmounts_without_transfer_and_refresh_rearms(tmp_path):
    _bay, controller, dock, _published = _ready(tmp_path, remote=False)

    reply = controller.request_eject(source="lcd")

    assert reply["status"] == "ejected"
    assert controller.snapshot()["state"] == "EJECTED"
    assert controller.snapshot()["safe_to_remove"] is True
    assert dock.calls[-1] == "release"

    controller.tick()
    assert controller.snapshot()["state"] == "EJECTED"  # stays ejected

    refreshed = controller.request_refresh(source="web")
    assert refreshed["ok"] is True
    assert controller.snapshot()["state"] == "READY"


def test_unregistered_labeled_drive_is_reported(tmp_path):
    bay, controller, dock, _button, _clock = rig(tmp_path)
    device = BlockDevice(
        path="/dev/sdj1",
        uuid="1234-ABCD",
        fstype="exfat",
        label="TV A-M",
        serial="SERIAL9",
        transport="usb",
        removable=True,
        mountpoints=(),
        size_bytes=1,
    )
    dock.scan = lambda: DockScan(
        docked=(), unknown_usb_filesystems=1, unregistered_labeled=(device,)
    )

    controller.tick()

    status = controller.snapshot()
    assert status["state"] == "UNREGISTERED"
    assert status["unregistered"][0]["uuid"] == "1234-ABCD"
    assert "TV A-M" in status["reason"]
    del bay
