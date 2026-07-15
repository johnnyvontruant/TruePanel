import pytest

from truepanel.lab.display_experiment import (
    DisplayExperiment,
    DisplayFrame,
    build_characterization,
)
from truepanel.lab.display_patterns import pattern


def test_empty_experiment():
    experiment = DisplayExperiment("demo")

    assert experiment.name == "demo"
    assert experiment.frames == []


def test_add_pattern_creates_frame():
    experiment = DisplayExperiment("demo")

    experiment.add(pattern("alphabet"))

    assert len(experiment.frames) == 1

    frame = experiment.frames[0]

    assert isinstance(frame, DisplayFrame)
    assert frame.line1 == "ABCDEFGHIJKLMNOP"
    assert frame.line2 == "QRSTUVWXYZ012345"


def test_custom_duration():
    experiment = DisplayExperiment("demo")

    experiment.add(
        pattern("numbers"),
        duration_seconds=2.5,
    )

    assert experiment.frames[0].duration_seconds == pytest.approx(
        2.5
    )


def test_characterization_contains_every_pattern():
    experiment = build_characterization()

    assert len(experiment.frames) == 4


def test_characterization_order():
    experiment = build_characterization()

    assert experiment.frames[0].line1 == "ABCDEFGHIJKLMNOP"
    assert experiment.frames[1].line1 == "0123456789ABCDEF"
    assert experiment.frames[2].line1 == "A1B2C3D4E5F6G7H8"
    assert experiment.frames[3].line1 == "################"


def test_characterization_name():
    experiment = build_characterization()

    assert experiment.name == "display-characterization"


def test_every_frame_has_duration():
    experiment = build_characterization(
        duration_seconds=0.75,
    )

    for frame in experiment.frames:
        assert frame.duration_seconds == pytest.approx(
            0.75
        )


def test_frames_are_display_frame_instances():
    experiment = build_characterization()

    assert all(
        isinstance(frame, DisplayFrame)
        for frame in experiment.frames
    )


def test_frame_is_immutable():
    frame = DisplayFrame(
        line1="ABCDEFGHIJKLMNOP",
        line2="QRSTUVWXYZ012345",
    )

    with pytest.raises(Exception):
        frame.line1 = "changed"
