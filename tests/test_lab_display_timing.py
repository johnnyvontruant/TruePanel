import pytest

from truepanel.lab.display_timing import (
    measure_clear,
    measure_display_operation,
    measure_frame_write,
    measure_line_write,
)


class FakeController:
    def __init__(self):
        self.calls = []

    def clear(self):
        self.calls.append(("clear",))

    def write_text(self, row, text):
        self.calls.append(
            ("write_text", row, text)
        )

    def write_frame(self, line1, line2):
        self.calls.append(
            ("write_frame", line1, line2)
        )


def test_measure_clear():
    controller = FakeController()

    result = measure_clear(
        controller,
        count=5,
    )

    assert result.operation == "clear"
    assert result.successes == 5
    assert len(controller.calls) == 5


def test_measure_line_write():
    controller = FakeController()

    result = measure_line_write(
        controller,
        row=0,
        text="HELLO",
        count=3,
    )

    assert result.successes == 3
    assert controller.calls == [
        ("write_text", 0, "HELLO"),
        ("write_text", 0, "HELLO"),
        ("write_text", 0, "HELLO"),
    ]


def test_measure_frame_write():
    controller = FakeController()

    result = measure_frame_write(
        controller,
        line1="ABC",
        line2="DEF",
        count=2,
    )

    assert result.successes == 2
    assert controller.calls == [
        ("write_frame", "ABC", "DEF"),
        ("write_frame", "ABC", "DEF"),
    ]


def test_callback_receives_every_sample():
    samples = []

    controller = FakeController()

    measure_clear(
        controller,
        count=4,
        callback=samples.append,
    )

    assert len(samples) == 4
    assert samples[0].index == 1
    assert samples[-1].index == 4


def test_invalid_row():
    controller = FakeController()

    with pytest.raises(ValueError):
        measure_line_write(
            controller,
            row=2,
            text="FAIL",
        )


def test_invalid_count():
    with pytest.raises(ValueError):
        measure_display_operation(
            operation="clear",
            execute=lambda: None,
            count=0,
        )


def test_invalid_interval():
    with pytest.raises(ValueError):
        measure_display_operation(
            operation="clear",
            execute=lambda: None,
            interval=-1,
        )


def test_failed_operation():
    def explode():
        raise RuntimeError("boom")

    result = measure_display_operation(
        operation="failure",
        execute=explode,
        count=2,
    )

    assert result.failures == 2
    assert result.successes == 0
    assert not result.healthy


def test_latency_summary_exists():
    controller = FakeController()

    result = measure_clear(
        controller,
        count=3,
    )

    assert result.latency.count == 3
