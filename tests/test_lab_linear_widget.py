import pytest

from truepanel.lab.widgets.linear import LinearWidget


def test_normalize_minimum():
    widget = LinearWidget()

    assert widget.normalize(0.0) == pytest.approx(0.0)


def test_normalize_midpoint():
    widget = LinearWidget()

    assert widget.normalize(0.5) == pytest.approx(0.5)


def test_normalize_maximum():
    widget = LinearWidget()

    assert widget.normalize(1.0) == pytest.approx(1.0)


def test_normalize_custom_range():
    widget = LinearWidget(
        minimum=20,
        maximum=80,
    )

    assert widget.normalize(50) == pytest.approx(0.5)


def test_normalize_clamps_low():
    widget = LinearWidget()

    assert widget.normalize(-10) == pytest.approx(0.0)


def test_normalize_clamps_high():
    widget = LinearWidget()

    assert widget.normalize(10) == pytest.approx(1.0)


def test_invalid_range():
    widget = LinearWidget(
        minimum=10,
        maximum=10,
    )

    with pytest.raises(
        ValueError,
        match="maximum must exceed minimum",
    ):
        widget.normalize(10)


def test_ascii_render():
    widget = LinearWidget(
        width=8,
        style="ascii",
    )

    assert widget.render(0.5) == "####----"


def test_block_render():
    widget = LinearWidget(
        width=8,
        style="blocks",
    )

    assert widget.render(0.5) == "████░░░░"


def test_dot_render():
    widget = LinearWidget(
        width=8,
        style="dots",
    )

    assert widget.render(0.5) == "••••····"
