"""
Tests for Project Stargate repeat experiments.

Run with:

    PYTHONPATH=. python3 tests/test_lab_experiments.py
"""

from __future__ import annotations

from truepanel.lab.experiments import (
    run_repeat_experiment,
)
from truepanel.lab.statistics import (
    percentile_nearest_rank,
    summarize_latencies,
)


class FakeController:
    def __init__(self):
        self.board_calls = 0
        self.button_calls = 0

    def query_board_id(self):
        self.board_calls += 1
        return 0x007D

    def query_protocol_version(self):
        return 0x0003

    def query_buttons(self):
        self.button_calls += 1

        if self.button_calls == 2:
            raise TimeoutError("simulated timeout")

        return 0x0000


def test_latency_summary():
    summary = summarize_latencies(
        [10.0, 20.0, 30.0, 40.0]
    )

    assert summary.count == 4
    assert summary.minimum_ms == 10.0
    assert summary.maximum_ms == 40.0
    assert summary.average_ms == 25.0
    assert summary.median_ms == 25.0
    assert summary.p95_ms == 40.0


def test_empty_latency_summary():
    summary = summarize_latencies([])

    assert summary.count == 0
    assert summary.minimum_ms is None
    assert summary.maximum_ms is None
    assert summary.average_ms is None
    assert summary.median_ms is None
    assert summary.p95_ms is None


def test_percentile_validation():
    try:
        percentile_nearest_rank([1.0], 101)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected invalid percentile to fail")


def test_repeat_success():
    controller = FakeController()

    result = run_repeat_experiment(
        controller,
        query="board",
        count=5,
        interval=0,
    )

    assert result.successes == 5
    assert result.failures == 0
    assert result.success_rate == 100.0
    assert result.values_consistent
    assert result.stable_value == 0x007D
    assert controller.board_calls == 5
    assert result.latency.count == 5


def test_repeat_records_individual_failure():
    controller = FakeController()

    result = run_repeat_experiment(
        controller,
        query="buttons",
        count=3,
        interval=0,
    )

    assert result.successes == 2
    assert result.failures == 1
    assert len(result.samples) == 3
    assert not result.samples[1].success
    assert "TimeoutError" in result.samples[1].error


def test_invalid_query():
    controller = FakeController()

    try:
        run_repeat_experiment(
            controller,
            query="warp-drive",
            count=1,
            interval=0,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Expected invalid query to fail")


def main():
    tests = [
        test_latency_summary,
        test_empty_latency_summary,
        test_percentile_validation,
        test_repeat_success,
        test_repeat_records_individual_failure,
        test_invalid_query,
    ]

    for test in tests:
        test()
        print(f"PASS: {test.__name__}")

    print()
    print("Project Stargate Mission 3B.3: PASS")


if __name__ == "__main__":
    main()
