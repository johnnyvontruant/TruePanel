from truepanel.history.black_box import BlackBoxFrame, BlackBoxReplay
from truepanel.history.black_box_narrator import BlackBoxIncidentNarrator


def replay(*frames):
    return BlackBoxReplay(frames)


def test_narrator_reports_meaningful_state_transitions_not_page_rotation():
    before = BlackBoxFrame.capture(
        captured_at=100,
        sequence=1,
        storage={"pool_health": "ONLINE"},
        fan={"rpm": [1500, 1450]},
        lcd={"available": True, "stale": False, "page": "show_truenas"},
        mission_control={"healthy": True},
        buttons={"button_reports": 3},
    )
    after = BlackBoxFrame.capture(
        captured_at=105,
        sequence=2,
        storage={"pool_health": "DEGRADED"},
        fan={"rpm": [0, 1450]},
        lcd={"available": True, "stale": False, "page": "show_pool_health"},
        mission_control={"healthy": True},
        buttons={"button_reports": 4},
    )

    events = BlackBoxIncidentNarrator(replay(before, after)).incidents()

    assert [(e.domain, e.severity) for e in events] == [
        ("storage", "warning"),
        ("fan", "warning"),
        ("buttons", "info"),
    ]
    assert all("show_pool_health" not in event.summary for event in events)


def test_narrator_reports_recovery_alert_lifecycle_and_availability():
    first = BlackBoxFrame.capture(
        captured_at=10,
        sequence=10,
        fan={"rpm": [0]},
        lcd={"available": True, "stale": True},
        mission_control={"available": False},
        alerts=[{"severity": "critical", "message": "Pool degraded"}],
    )
    second = BlackBoxFrame.capture(
        captured_at=20,
        sequence=11,
        fan={"rpm": [1500]},
        lcd={"available": True, "stale": False},
        mission_control={"available": True},
        alerts=[],
    )

    events = BlackBoxIncidentNarrator(replay(first, second)).incidents()
    summaries = [event.summary for event in events]

    assert "Fan 1 RPM recovered from 0 to 1500." in summaries
    assert "Alert cleared: Pool degraded" in summaries
    assert "Mission Control became available." in summaries
    assert "LCD state returned to fresh." in summaries


def test_new_alert_keeps_recorded_severity_and_timeline_is_deterministic():
    first = BlackBoxFrame.capture(captured_at=1, sequence=1)
    second = BlackBoxFrame.capture(
        captured_at=2.5,
        sequence=2,
        alerts=[{"severity": "critical", "message": "Fan stopped"}],
    )

    narrator = BlackBoxIncidentNarrator(replay(first, second))
    event = narrator.incidents()[0]

    assert event.severity == "critical"
    assert event.summary == "Alert observed: Fan stopped"
    assert narrator.timeline() == (
        "t=2.500 seq=2 [critical] alerts: Alert observed: Fan stopped",
    )


def test_narrator_caps_event_count_and_summary_size():
    first = BlackBoxFrame.capture(captured_at=1, sequence=1)
    second = BlackBoxFrame.capture(
        captured_at=2,
        sequence=2,
        alerts=[
            {"severity": "warning", "message": "x" * 500},
            {"severity": "warning", "message": "y" * 500},
        ],
    )

    events = BlackBoxIncidentNarrator(
        replay(first, second),
        max_events=1,
        max_summary_chars=80,
    ).incidents()

    assert len(events) == 1
    assert len(events[0].summary) <= 80
    assert events[0].summary.endswith("…")


def test_narrator_requires_black_box_replay():
    try:
        BlackBoxIncidentNarrator([])
    except TypeError as error:
        assert "BlackBoxReplay" in str(error)
    else:
        raise AssertionError("expected TypeError")
