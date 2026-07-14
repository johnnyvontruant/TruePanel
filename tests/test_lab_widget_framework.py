from truepanel.lab.widgets import (
    ProgressBar,
    registry,
)


def test_progress_registered():
    assert "progress" in registry


def test_lookup():
    widget = registry.get(
        "progress"
    )

    assert widget is ProgressBar


def test_ascii_style():
    bar = ProgressBar(
        style="ascii"
    )

    assert (
        bar.render(0.5)
        == "########--------"
    )


def test_block_style():
    bar = ProgressBar(
        style="blocks"
    )

    assert (
        bar.render(0.5)
        == "████████░░░░░░░░"
    )


def test_dot_style():
    bar = ProgressBar(
        style="dots"
    )

    assert (
        bar.render(0.5)
        == "••••••••········"
    )
