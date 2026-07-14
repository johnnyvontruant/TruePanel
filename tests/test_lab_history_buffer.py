import pytest

from truepanel.lab.widgets.history import (
    HistoryBuffer,
)


def test_empty_buffer():
    history = HistoryBuffer()

    assert history.values() == ()
    assert history.latest is None
    assert len(history) == 0
    assert history.full is False


def test_append():
    history = HistoryBuffer()

    history.append(1)

    assert history.values() == (1.0,)
    assert history.latest == pytest.approx(1.0)


def test_extend():
    history = HistoryBuffer()

    history.extend([1, 2, 3])

    assert history.values() == (
        1.0,
        2.0,
        3.0,
    )


def test_discards_oldest_values():
    history = HistoryBuffer(size=3)

    history.extend([1, 2, 3, 4])

    assert history.values() == (
        2.0,
        3.0,
        4.0,
    )


def test_initial_values():
    history = HistoryBuffer(
        size=3,
        initial=[1, 2],
    )

    assert history.values() == (
        1.0,
        2.0,
    )


def test_initial_values_respect_limit():
    history = HistoryBuffer(
        size=3,
        initial=[1, 2, 3, 4],
    )

    assert history.values() == (
        2.0,
        3.0,
        4.0,
    )


def test_clear():
    history = HistoryBuffer()

    history.extend([1, 2, 3])
    history.clear()

    assert history.values() == ()
    assert history.latest is None


def test_full():
    history = HistoryBuffer(size=2)

    history.append(1)

    assert history.full is False

    history.append(2)

    assert history.full is True


def test_iteration():
    history = HistoryBuffer(
        initial=[1, 2, 3],
    )

    assert list(history) == [
        1.0,
        2.0,
        3.0,
    ]


def test_invalid_size():
    with pytest.raises(
        ValueError,
        match="size must be at least 1",
    ):
        HistoryBuffer(size=0)
