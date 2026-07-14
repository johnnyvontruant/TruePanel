from truepanel.lab.widgets import (
    Sparkline,
    registry,
)


def test_registered():
    assert registry.get(
        "sparkline"
    ) is Sparkline


def test_empty():
    graph = Sparkline()

    assert graph.render([]) == ""


def test_single():
    graph = Sparkline()

    assert graph.render([1.0]) == "█"


def test_all_levels():
    graph = Sparkline(width=8)

    values = [
        0.0,
        1 / 7,
        2 / 7,
        3 / 7,
        4 / 7,
        5 / 7,
        6 / 7,
        1.0,
    ]

    assert (
        graph.render(values)
        == "▁▂▃▄▅▆▇█"
    )


def test_width_limit():
    graph = Sparkline(width=4)

    values = [
        0,
        0,
        0,
        0,
        1,
        1,
    ]

    assert graph.render(values) == "▁▁██"


def test_clamps():
    graph = Sparkline(width=2)

    assert graph.render(
        [-5, 5]
    ) == "▁█"
