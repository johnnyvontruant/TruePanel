import pytest

from truepanel.lab.widgets import (
    Spinner,
    registry,
)


def test_registered():
    assert registry.get(
        "spinner"
    ) is Spinner


def test_first_frame():
    spinner = Spinner()

    assert spinner.render(0) == "|"


def test_second_frame():
    spinner = Spinner()

    assert spinner.render(1) == "/"


def test_wraps():
    spinner = Spinner()

    assert spinner.render(4) == "|"


def test_frame_count():
    spinner = Spinner()

    assert spinner.frame_count == 4


def test_custom_frames():
    spinner = Spinner(
        frames=("A", "B", "C")
    )

    assert spinner.render(5) == "C"


def test_empty_frames():
    with pytest.raises(ValueError):
        Spinner(
            frames=()
        ).render(0)
