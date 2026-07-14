from truepanel.lab.widgets import (
    SignalMeter,
    registry,
)


def test_registered():
    assert registry.get(
        "signal"
    ) is SignalMeter


def test_zero():
    meter = SignalMeter()

    assert (
        meter.render(0)
        == "░░░░░░░░░░░░░░░░"
    )


def test_half():
    meter = SignalMeter()

    assert (
        meter.render(0.5)
        == "████████░░░░░░░░"
    )


def test_full():
    meter = SignalMeter()

    assert (
        meter.render(1.0)
        == "████████████████"
    )


def test_percent():
    meter = SignalMeter()

    assert (
        meter.render_percent(25)
        == "████░░░░░░░░░░░░"
    )
