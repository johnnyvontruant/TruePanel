import pytest

from truepanel.lab.widgets import (
    Thermometer,
    registry,
)


def test_registered():
    assert registry.get(
        "thermometer"
    ) is Thermometer


def test_empty():
    widget = Thermometer()

    assert (
        widget.render(0)
        == "░░░░░░░░░░░░░░░░"
    )


def test_half():
    widget = Thermometer()

    assert (
        widget.render(50)
        == "████████░░░░░░░░"
    )


def test_full():
    widget = Thermometer()

    assert (
        widget.render(100)
        == "████████████████"
    )


def test_custom_range():
    widget = Thermometer(
        minimum=20,
        maximum=80,
    )

    assert (
        widget.render(50)
        == "████████░░░░░░░░"
    )


def test_low_clamped():
    widget = Thermometer()

    assert (
        widget.render(-10)
        == "░░░░░░░░░░░░░░░░"
    )


def test_high_clamped():
    widget = Thermometer()

    assert (
        widget.render(500)
        == "████████████████"
    )


def test_invalid_range():
    with pytest.raises(ValueError):
        Thermometer(
            minimum=10,
            maximum=10,
        ).render(10)
