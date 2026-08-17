from dataclasses import dataclass

import pytest

from truepanel.history.black_box_api import (
    BlackBoxReplayAPI,
    normalize_scenario_request,
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
            "lcd": {},
            "incidents": [],
        }


class Incident:
    def __init__(self, sequence):
        self.sequence = sequence

    def as_dict(self):
        return {
            "sequence": self.sequence,
            "domain": "storage",
        }


class Replay:
    def __init__(self, count=3):
        self.frames = tuple(
            Frame(index, float(index * 10))
            for index in range(1, count + 1)
        )
        self.duration_seconds = (
            0.0
            if count < 2
            else self.frames[-1].captured_at - self.frames[0].captured_at
        )


class Session:
    def __init__(self, count=3, incidents=2):
        self.replay = Replay(count)
        self.incidents = tuple(
            Incident(index)
            for index in range(incidents)
        )
        self.simulation_only = False

    def at_sequence(self, sequence):
        if any(
            frame.sequence == sequence
            for frame in self.replay.frames
        ):
            return View(sequence)
        return None

    def at_or_before(self, captured_at):
        matches = [
            frame
            for frame in self.replay.frames
            if frame.captured_at <= captured_at
        ]
        return None if not matches else View(matches[-1].sequence)


def test_metadata_is_read_only_and_bounded_to_recording():
    payload = BlackBoxReplayAPI(Session()).metadata()
    assert payload["read_only"] is True
    assert payload["frame_count"] == 3
    assert payload["first_sequence"] == 1
    assert payload["last_sequence"] == 3
    assert payload["duration_seconds"] == 20.0
    assert payload["simulation_only"] is False


def test_frame_seek_and_timeline_are_data_only_views():
    api = BlackBoxReplayAPI(Session())
    assert api.frame(2)["frame"]["sequence"] == 2
    assert api.frame(99) is None
    assert api.seek(25.0)["frame"]["sequence"] == 2
    assert api.seek(5.0) is None

    payload = api.timeline(start_sequence=2, limit=1)
    assert [
        item["frame"]["sequence"]
        for item in payload["items"]
    ] == [2]
    assert payload["truncated"] is True


def test_timeline_and_incident_limits_fail_closed():
    api = BlackBoxReplayAPI(Session(count=3, incidents=3))
    with pytest.raises(ValueError):
        api.timeline(limit=0)
    with pytest.raises(ValueError):
        api.timeline(start_sequence=3, end_sequence=2)
    with pytest.raises(ValueError):
        api.incident_history(limit=0)

    incidents = api.incident_history(limit=2)
    assert incidents["count"] == 2
    assert incidents["truncated"] is True


def test_scenario_contract_only_accepts_bounded_known_faults():
    normalized = normalize_scenario_request(
        {
            3: "fan_stall",
            1: "lcd_stale",
        }
    )
    assert normalized == {
        1: "lcd_stale",
        3: "fan_stall",
    }

    api = BlackBoxReplayAPI(Session())
    contract = api.scenario_contract()
    assert contract["read_only"] is True
    assert contract["simulation_only"] is True
    assert "storage_degraded" in contract["supported_faults"]

    with pytest.raises(ValueError):
        normalize_scenario_request({1: "shell_command"})
    with pytest.raises(ValueError):
        normalize_scenario_request({-1: "fan_stall"})


def test_invalid_session_contract_is_rejected():
    with pytest.raises(TypeError):
        BlackBoxReplayAPI(object())
