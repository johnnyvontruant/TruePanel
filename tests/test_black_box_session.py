import pytest

from truepanel.history.black_box import BlackBoxFrame, BlackBoxRecorder, BlackBoxReplay
from truepanel.history.black_box_chaos import BlackBoxChaosFault, BlackBoxChaosScenario
from truepanel.history.black_box_compatibility import (
    CompatibilityReplayCheck,
    CompatibilityReplayProfile,
)
from truepanel.history.black_box_session import BlackBoxReplaySession


def make_replay():
    return BlackBoxReplay(
        (
            BlackBoxFrame.capture(
                captured_at=10.0,
                sequence=1,
                lcd={"page": "show_pool", "line1": "Pool", "line2": "ONLINE"},
                storage={"health": "ONLINE"},
            ),
            BlackBoxFrame.capture(
                captured_at=20.0,
                sequence=2,
                lcd={"page": "show_pool", "line1": "Pool", "line2": "ONLINE"},
                storage={"health": "ONLINE"},
            ),
        )
    )


def test_session_projects_chaos_without_mutating_source():
    source = make_replay()
    scenario = BlackBoxChaosScenario({2: BlackBoxChaosFault("storage_degraded")})
    session = BlackBoxReplaySession(source, chaos=scenario)

    assert source.at_sequence(2).storage["health"] == "ONLINE"
    view = session.at_sequence(2)
    assert view.frame.storage["health"] == "DEGRADED"
    assert view.lcd.page == "show_pool"
    assert any(event.domain == "storage" for event in view.incidents)


def test_replacing_chaos_starts_from_pristine_source():
    scenario = BlackBoxChaosScenario({2: BlackBoxChaosFault("storage_degraded")})
    simulated = BlackBoxReplaySession(make_replay(), chaos=scenario)
    clean = simulated.with_chaos(None)

    assert simulated.at_sequence(2).frame.storage["health"] == "DEGRADED"
    assert clean.at_sequence(2).frame.storage["health"] == "ONLINE"
    assert clean.simulation_only is False


def test_session_can_load_recorder(tmp_path):
    recorder = BlackBoxRecorder(tmp_path / "recording.jsonl")
    for frame in make_replay().frames:
        recorder.append(frame)

    session = BlackBoxReplaySession.from_recorder(recorder)
    assert [view.frame.sequence for view in session.timeline] == [1, 2]


def test_session_inherits_recorder_replay_limit(tmp_path):
    recorder = BlackBoxRecorder(
        tmp_path / "recording.jsonl",
        max_replay_frames=1,
    )
    for frame in make_replay().frames:
        recorder.append(frame)

    with pytest.raises(ValueError, match="frame limit exceeded"):
        BlackBoxReplaySession.from_recorder(recorder)


def test_compatibility_session_does_not_invent_lcd_state():
    profile = CompatibilityReplayProfile(
        source_schema_version=1,
        source_truepanel_version="1.2.0rc1",
        source_generated_at="2026-08-14T00:00:00+00:00",
        classification="SUPPORTED",
        installation_mode="native",
        hardware_control="locked",
        checks=(CompatibilityReplayCheck(status="PASS", name="OS", detail="TrueNAS"),),
    )

    session = BlackBoxReplaySession.from_compatibility_profile(profile, captured_at=30.0)
    view = session.timeline[0]

    assert view.frame.telemetry["compatibility_replay"]["simulation_only"] is True
    assert view.lcd.available is False
    assert view.lcd.page == "unavailable"


def test_session_views_are_browser_safe_dicts():
    view = BlackBoxReplaySession(make_replay(), lcd_width=8).at_or_before(20.0)
    payload = view.as_dict()

    assert payload["frame"]["sequence"] == 2
    assert payload["lcd"]["line1"] == "Pool    "
    assert isinstance(payload["incidents"], list)
