from truepanel.history.black_box import BlackBoxFrame, BlackBoxReplay
from truepanel.history.black_box_twin import (
    BlackBoxDigitalTwin,
    project_lcd_state,
)


def twin_replay():
    return BlackBoxReplay(
        [
            BlackBoxFrame.capture(
                captured_at=10.0,
                sequence=1,
                lcd={
                    "page": "show_truenas",
                    "line1": "TrueNAS",
                    "line2": "25.10.5",
                    "source": "runtime",
                    "stale": False,
                    "available": True,
                },
            ),
            BlackBoxFrame.capture(
                captured_at=15.0,
                sequence=2,
                lcd={
                    "page": "show_pool_health",
                    "line1": "Pool health is ONLINE and verbose",
                    "line2": "ONLINE",
                },
            ),
        ]
    )


def test_lcd_projection_is_fixed_width_and_data_only():
    state = project_lcd_state(twin_replay().frames[0])

    assert state.page == "show_truenas"
    assert state.line1 == "TrueNAS         "
    assert state.line2 == "25.10.5         "
    assert state.source == "runtime"
    assert state.available is True
    assert state.stale is False


def test_lcd_projection_truncates_without_mutating_recorded_frame():
    replay = twin_replay()
    original = replay.frames[1].lcd["line1"]

    state = project_lcd_state(replay.frames[1], width=10)

    assert state.line1 == "Pool healt"
    assert replay.frames[1].lcd["line1"] == original


def test_digital_twin_supports_deterministic_replay_queries():
    twin = BlackBoxDigitalTwin(twin_replay())

    assert [state.sequence for state in twin.timeline] == [1, 2]
    assert twin.at_sequence(2).page == "show_pool_health"
    assert twin.at_sequence(999) is None
    assert twin.at_or_before(9.9) is None
    assert twin.at_or_before(12).sequence == 1
    assert [
        state.sequence
        for state in twin.between(10, 15)
    ] == [1, 2]


def test_missing_lcd_payload_projects_safe_unavailable_state():
    frame = BlackBoxFrame.capture(captured_at=1.0, sequence=1)

    state = project_lcd_state(frame)

    assert state.page == "unavailable"
    assert state.line1 == " " * 16
    assert state.line2 == " " * 16
    assert state.source == "black-box"
    assert state.available is False


def test_digital_twin_rejects_invalid_width_or_non_replay():
    replay = twin_replay()

    for width in (0, 257):
        try:
            BlackBoxDigitalTwin(replay, width=width)
        except ValueError as error:
            assert "between 1 and 256" in str(error)
        else:
            raise AssertionError("invalid width was accepted")

    try:
        BlackBoxDigitalTwin(object())
    except TypeError as error:
        assert "BlackBoxReplay" in str(error)
    else:
        raise AssertionError("non-replay object was accepted")
