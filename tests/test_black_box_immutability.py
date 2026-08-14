from truepanel.history.black_box import BlackBoxFrame, BlackBoxReplay


def test_replay_defensively_copies_input_and_returned_frames():
    source = BlackBoxFrame.capture(
        captured_at=100.0,
        sequence=10,
        lcd={"page": "show_truenas", "line1": "TrueNAS"},
    )
    replay = BlackBoxReplay((source,))

    source.lcd["page"] = "mutated-input"
    assert replay.at_sequence(10).lcd["page"] == "show_truenas"

    returned = replay.at_sequence(10)
    returned.lcd["page"] = "mutated-output"
    assert replay.at_sequence(10).lcd["page"] == "show_truenas"

    exposed = replay.frames[0]
    exposed.lcd["page"] = "mutated-frames-property"
    assert replay.frames[0].lcd["page"] == "show_truenas"

    cursor = replay.cursor()
    cursor.current.lcd["page"] = "mutated-cursor"
    assert cursor.current.lcd["page"] == "show_truenas"
