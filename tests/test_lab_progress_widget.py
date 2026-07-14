import pytest

from truepanel.lab.widgets.progress import (
    ProgressBar,
)


def test_zero():
    bar = ProgressBar()

    assert (
        bar.render(0.0)
        == "----------------"
    )


def test_half():
    bar = ProgressBar()

    assert (
        bar.render(0.5)
        == "########--------"
    )


def test_full():
    bar = ProgressBar()

    assert (
        bar.render(1.0)
        == "################"
    )


def test_clamps_negative():
    bar = ProgressBar()

    assert (
        bar.render(-5)
        == "----------------"
    )


def test_clamps_large():
    bar = ProgressBar()

    assert (
        bar.render(5)
        == "################"
    )


def test_percent():
    bar = ProgressBar()

    assert (
        bar.render_percent(25)
        == "####------------"
    )


def test_custom_width():
    bar = ProgressBar(width=8)

    assert (
        bar.render(0.5)
        == "####----"
    )


def test_block_style():
    bar = ProgressBar(
        width=8,
        style="blocks",
    )

    assert (
        bar.render(0.5)
        == "████░░░░"
    )


def test_invalid_width():
    with pytest.raises(ValueError):
        ProgressBar(width=0)
