from dataclasses import dataclass
from pathlib import Path
import ast

from truepanel.history.black_box_api import BlackBoxReplayAPI
from truepanel.history.black_box_mission_control import (
    BlackBoxMissionControlReplayAdapter,
    ReplayRouteRequest,
)


@dataclass(frozen=True)
class Frame:
    sequence: int
    captured_at: float


class View:
    def __init__(self, sequence):
        self.sequence = sequence

    def as_dict(self):
        return {
            "frame": {"sequence": self.sequence},
            "lcd": {"line1": "Replay", "line2": str(self.sequence)},
            "incidents": [],
        }


class Incident:
    def __init__(self, sequence):
        self.sequence = sequence

    def as_dict(self):
        return {"sequence": self.sequence, "domain": "storage"}


class Replay:
    def __init__(self):
        self.frames = (
            Frame(1, 10.0),
            Frame(2, 20.0),
            Frame(3, 30.0),
        )
        self.duration_seconds = 20.0


class Session:
    def __init__(self):
        self.replay = Replay()
        self.incidents = (Incident(2),)
        self.simulation_only = False

    def at_sequence(self, sequence):
        return (
            View(sequence)
            if any(frame.sequence == sequence for frame in self.replay.frames)
            else None
        )

    def at_or_before(self, captured_at):
        matches = [
            frame
            for frame in self.replay.frames
            if frame.captured_at <= captured_at
        ]
        return None if not matches else View(matches[-1].sequence)


def make_adapter():
    return BlackBoxMissionControlReplayAdapter(
        BlackBoxReplayAPI(Session())
    )


def test_metadata_frame_and_seek_routes_are_read_only_views():
    adapter = make_adapter()

    metadata = adapter.handle(ReplayRouteRequest("GET", "/api/v1/replay"))
    assert metadata.status == 200
    assert metadata.body["read_only"] is True
    assert metadata.body["frame_count"] == 3

    frame = adapter.handle(
        ReplayRouteRequest("GET", "/api/v1/replay/frame/2")
    )
    assert frame.status == 200
    assert frame.body["frame"]["sequence"] == 2

    seek = adapter.handle(
        ReplayRouteRequest(
            "GET",
            "/api/v1/replay/seek?captured_at=25",
        )
    )
    assert seek.status == 200
    assert seek.body["frame"]["sequence"] == 2


def test_timeline_incidents_and_chaos_contract_are_bounded_data():
    adapter = make_adapter()

    timeline = adapter.handle(
        ReplayRouteRequest(
            "GET",
            "/api/v1/replay/timeline?start_sequence=2&limit=1",
        )
    )
    assert timeline.status == 200
    assert timeline.body["count"] == 1
    assert timeline.body["items"][0]["frame"]["sequence"] == 2

    incidents = adapter.handle(
        ReplayRouteRequest("GET", "/api/v1/replay/incidents?limit=1")
    )
    assert incidents.status == 200
    assert incidents.body["count"] == 1

    chaos = adapter.handle(
        ReplayRouteRequest("GET", "/api/v1/replay/chaos")
    )
    assert chaos.status == 200
    assert chaos.body["read_only"] is True
    assert chaos.body["simulation_only"] is True


def test_missing_frames_and_unknown_routes_fail_closed():
    adapter = make_adapter()

    missing = adapter.handle(
        ReplayRouteRequest("GET", "/api/v1/replay/frame/99")
    )
    assert missing.status == 404
    assert missing.body["error"]["code"] == "frame_not_found"

    unknown = adapter.handle(
        ReplayRouteRequest("GET", "/api/v1/replay/nope")
    )
    assert unknown.status == 404
    assert unknown.body["error"]["code"] == "route_not_found"


def test_non_get_and_malformed_query_are_rejected():
    adapter = make_adapter()

    post = adapter.handle(
        ReplayRouteRequest("POST", "/api/v1/replay")
    )
    assert post.status == 405
    assert post.body["read_only"] is True

    unknown_field = adapter.handle(
        ReplayRouteRequest("GET", "/api/v1/replay/timeline?shell=1")
    )
    assert unknown_field.status == 400

    duplicate = adapter.handle(
        ReplayRouteRequest(
            "GET",
            "/api/v1/replay/timeline?limit=1&limit=2",
        )
    )
    assert duplicate.status == 400

    bad_number = adapter.handle(
        ReplayRouteRequest("GET", "/api/v1/replay/frame/not-a-number")
    )
    assert bad_number.status == 400


def test_adapter_module_has_no_live_runtime_or_hardware_imports():
    source = Path(
        "truepanel/history/black_box_mission_control.py"
    ).read_text(encoding="utf-8")

    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")

    forbidden = (
        "truepanel.web",
        "truepanel.hardware",
        "truepanel.host",
        "subprocess",
        "serial",
        "socket",
    )
    assert not any(
        module == prefix or module.startswith(prefix + ".")
        for module in imports
        for prefix in forbidden
    )
