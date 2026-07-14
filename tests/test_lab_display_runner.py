import pytest

from truepanel.lab.display_experiment import (
    DisplayExperiment,
)
from truepanel.lab.display_patterns import pattern
from truepanel.lab.display_runner import (
    DisplayExperimentRunner,
)


class FakeController:
    def __init__(self):
        self.calls = []

    def clear(self):
        self.calls.append(("clear",))

    def write_frame(
        self,
        line1,
        line2,
    ):
        self.calls.append(
            (
                "write",
                line1,
                line2,
            )
        )


def build_experiment():
    experiment = DisplayExperiment("demo")

    experiment.add(
        pattern("alphabet"),
        duration_seconds=0.5,
    )

    experiment.add(
        pattern("numbers"),
        duration_seconds=1.0,
    )

    return experiment


def test_runner_clears_before_and_after():
    controller = FakeController()

    runner = DisplayExperimentRunner(
        controller,
        sleep=lambda _: None,
    )

    runner.run(build_experiment())

    assert controller.calls[0] == ("clear",)
    assert controller.calls[-1] == ("clear",)


def test_runner_writes_every_frame():
    controller = FakeController()

    runner = DisplayExperimentRunner(
        controller,
        sleep=lambda _: None,
    )

    runner.run(build_experiment())

    writes = [
        call
        for call in controller.calls
        if call[0] == "write"
    ]

    assert len(writes) == 2

    assert writes[0][1] == "ABCDEFGHIJKLMNOP"
    assert writes[1][1] == "0123456789ABCDEF"


def test_sleep_called_for_each_frame():
    sleeps = []

    controller = FakeController()

    runner = DisplayExperimentRunner(
        controller,
        sleep=sleeps.append,
    )

    runner.run(build_experiment())

    assert sleeps == [
        0.5,
        1.0,
    ]


def test_callback_receives_every_frame():
    callbacks = []

    controller = FakeController()

    runner = DisplayExperimentRunner(
        controller,
        sleep=lambda _: None,
    )

    runner.run(
        build_experiment(),
        callback=callbacks.append,
    )

    assert len(callbacks) == 2

    assert callbacks[0].index == 1
    assert callbacks[1].index == 2

    assert callbacks[0].total == 2
    assert callbacks[1].total == 2


def test_callback_receives_correct_pattern():
    callback_data = []

    controller = FakeController()

    runner = DisplayExperimentRunner(
        controller,
        sleep=lambda _: None,
    )

    runner.run(
        build_experiment(),
        callback=callback_data.append,
    )

    assert (
        callback_data[0].frame.line1
        == "ABCDEFGHIJKLMNOP"
    )

    assert (
        callback_data[1].frame.line1
        == "0123456789ABCDEF"
    )


def test_runner_accepts_empty_experiment():
    controller = FakeController()

    runner = DisplayExperimentRunner(
        controller,
        sleep=lambda _: None,
    )

    runner.run(DisplayExperiment("empty"))

    assert controller.calls == [
        ("clear",),
        ("clear",),
    ]


def test_frame_execution_total_matches():
    callback_data = []

    controller = FakeController()

    runner = DisplayExperimentRunner(
        controller,
        sleep=lambda _: None,
    )

    runner.run(
        build_experiment(),
        callback=callback_data.append,
    )

    assert all(
        item.total == 2
        for item in callback_data
    )
