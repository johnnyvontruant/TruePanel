import json

import pytest

from truepanel.history.black_box import (
    MAX_BLACK_BOX_REPLAY_FRAMES,
    BlackBoxFrame,
    BlackBoxRecorder,
    BlackBoxReplay,
)
from truepanel.holodeck.compiler import IncidentCompiler


def frame(sequence, *, fault=None, secret=None):
    return BlackBoxFrame.capture(
        captured_at=100.0 + sequence,
        sequence=sequence,
        telemetry={"fault": fault, "hostname": secret},
    )


def test_compiler_minimizes_window_and_removable_frames():
    replay = BlackBoxReplay(
        [
            frame(0),
            frame(1, fault="armed"),
            frame(2),
            frame(3, fault="triggered"),
            frame(4),
        ]
    )

    def violation(frames):
        values = {item.telemetry.get("fault") for item in frames}
        return {"armed", "triggered"} <= values

    result = IncidentCompiler(
        violation,
        invariant_id="thermal.arm_then_trigger",
    ).compile(replay, name="minimal-thermal-failure")

    assert result.manifest["source_sequences"] == [1, 3]
    assert result.manifest["window_frame_count"] == 3
    assert result.manifest["minimized_frame_count"] == 2
    assert [item["at"] for item in result.scenario["frames"]] == [0.0, 2.0]
    assert result.manifest["executable_code_generated"] is False


def test_compiler_accepts_recording_and_is_deterministic(tmp_path):
    recorder = BlackBoxRecorder(tmp_path / "incident.jsonl")
    recorder.append(frame(0))
    recorder.append(frame(1, fault="bad"))

    def predicate(frames):
        return any(item.telemetry.get("fault") == "bad" for item in frames)

    first = IncidentCompiler(predicate, invariant_id="fault.bad").compile(recorder)
    second = IncidentCompiler(predicate, invariant_id="fault.bad").compile(recorder.path)

    assert first.as_dict() == second.as_dict()
    json.dumps(first.as_dict(), allow_nan=False)


def test_compiler_output_is_privacy_safe_and_defensively_copied():
    source = frame(0, fault="bad", secret="private-host")
    replay = BlackBoxReplay([source])
    result = IncidentCompiler(lambda frames: True, invariant_id="always").compile(replay)

    scenario = result.scenario
    assert scenario["frames"][0]["telemetry"]["hostname"] == "<redacted>"
    scenario["frames"][0]["telemetry"]["fault"] = "mutated"
    assert result.scenario["frames"][0]["telemetry"]["fault"] == "bad"
    assert replay.frames[0].telemetry["fault"] == "bad"


def test_destructive_evaluator_cannot_mutate_source_or_candidates():
    replay = BlackBoxReplay([frame(0), frame(1, fault="bad")])

    def destructive(frames):
        reproduces = any(item.telemetry.get("fault") == "bad" for item in frames)
        for item in frames:
            item.telemetry.clear()
        return reproduces

    result = IncidentCompiler(destructive, invariant_id="mutation.safe").compile(replay)
    assert result.manifest["source_sequences"] == [1]
    assert replay.frames[1].telemetry["fault"] == "bad"


def test_work_is_bounded_and_limit_is_reported():
    replay = BlackBoxReplay([frame(index, fault="bad") for index in range(8)])
    result = IncidentCompiler(
        lambda frames: bool(frames),
        invariant_id="bounded",
        max_evaluations=1,
    ).compile(replay)

    assert result.manifest["evaluations"] == 1
    assert result.manifest["budget_exhausted"] is True
    assert result.manifest["minimized_frame_count"] <= 8


def test_rejects_nonviolating_empty_and_oversized_sources():
    compiler = IncidentCompiler(lambda frames: False, invariant_id="missing")
    with pytest.raises(ValueError, match="at least one"):
        compiler.compile(BlackBoxReplay([]))
    with pytest.raises(ValueError, match="does not reproduce"):
        compiler.compile(BlackBoxReplay([frame(0)]))
    with pytest.raises(ValueError, match="frame limit"):
        IncidentCompiler(
            lambda frames: True,
            invariant_id="large",
            max_frames=1,
        ).compile(BlackBoxReplay([frame(0), frame(1)]))


def test_compiler_cannot_raise_authoritative_replay_frame_limit():
    with pytest.raises(ValueError, match="max_frames must be between"):
        IncidentCompiler(
            lambda frames: True,
            invariant_id="large",
            max_frames=MAX_BLACK_BOX_REPLAY_FRAMES + 1,
        )


def test_compiler_path_uses_bounded_recorder_loader(tmp_path, monkeypatch):
    path = tmp_path / "incident.jsonl"
    path.write_text("not materialized")

    def reject_before_materialization(self):
        raise ValueError("bounded loader invoked")

    monkeypatch.setattr(
        BlackBoxRecorder,
        "load_replay",
        reject_before_materialization,
    )

    with pytest.raises(ValueError, match="bounded loader invoked"):
        IncidentCompiler(
            lambda frames: True,
            invariant_id="bounded",
        ).compile(path)
