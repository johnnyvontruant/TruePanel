from truepanel.lab.widgets import (
    BatteryMeter,
    registry,
)


def test_registered():
    assert registry.get(
        "battery"
    ) is BatteryMeter


def test_empty():
    widget = BatteryMeter()

    assert (
        widget.render_charge(0)
        == "░░░░░░░░░░░░░░░░"
    )


def test_half():
    widget = BatteryMeter()

    assert (
        widget.render_charge(50)
        == "████████░░░░░░░░"
    )


def test_full():
    widget = BatteryMeter()

    assert (
        widget.render_charge(100)
        == "████████████████"
    )


def test_clamped():
    widget = BatteryMeter()

    assert (
        widget.render_charge(500)
        == "████████████████"
    )
