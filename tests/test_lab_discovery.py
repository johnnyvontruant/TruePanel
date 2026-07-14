"""
Tests for the Project Stargate Discovery Engine.

Run with:

    PYTHONPATH=. python3 tests/test_lab_discovery.py
"""

from __future__ import annotations

from truepanel.lab.classifier import (
    ResponseClassification,
)
from truepanel.lab.discovery import (
    DiscoveryProbe,
    build_a125_probes,
    run_discovery,
    run_probe,
    validate_discovery_plan,
)


class FakeController:
    def query_board_id(self):
        return 0x007D

    def query_protocol_version(self):
        return 0x0003

    def query_buttons(self):
        return 0x0000


class FailingController(FakeController):
    def query_protocol_version(self):
        raise TimeoutError("simulated protocol timeout")


def test_build_plan():
    probes = build_a125_probes(FakeController())

    assert [probe.name for probe in probes] == [
        "board",
        "version",
        "buttons",
    ]

    assert [probe.opcode for probe in probes] == [
        0x00,
        0x07,
        0x06,
    ]


def test_safe_plan_validation():
    probes = build_a125_probes(FakeController())
    validate_discovery_plan(probes)


def test_experimental_plan_rejected():
    probes = [
        DiscoveryProbe(
            name="experimental",
            opcode=0x10,
            expected_response=0x42,
            query=lambda: 0,
        )
    ]

    try:
        validate_discovery_plan(probes)
    except PermissionError:
        pass
    else:
        raise AssertionError(
            "Experimental discovery plan should be rejected"
        )


def test_documented_write_rejected():
    probes = [
        DiscoveryProbe(
            name="display-write",
            opcode=0x0C,
            expected_response=0xFA,
            query=lambda: 0,
        )
    ]

    try:
        validate_discovery_plan(probes)
    except PermissionError:
        pass
    else:
        raise AssertionError(
            "Documented write should be rejected"
        )


def test_probe_success():
    probe = build_a125_probes(FakeController())[0]
    result = run_probe(probe)

    assert result.success
    assert result.value == 0x007D
    assert result.value_hex == "0x007D"
    assert (
        result.response.classification
        == ResponseClassification.KNOWN_RESPONSE
    )


def test_discovery_success():
    report = run_discovery(FakeController())

    assert report.healthy
    assert report.successes == 3
    assert report.failures == 0
    assert report.board_id == 0x007D
    assert report.protocol_version == 0x0003
    assert report.button_status == 0x0000
    assert len(report.results) == 3
    assert len(report.observations) == 3
    assert report.latency.count == 3


def test_discovery_records_failure():
    report = run_discovery(FailingController())

    assert not report.healthy
    assert report.successes == 2
    assert report.failures == 1
    assert report.board_id == 0x007D
    assert report.protocol_version is None

    failed = [
        result
        for result in report.results
        if not result.success
    ]

    assert len(failed) == 1
    assert (
        failed[0].response.classification
        == ResponseClassification.TIMEOUT
    )


def test_probe_callback():
    observed = []

    run_discovery(
        FakeController(),
        probe_callback=observed.append,
    )

    assert len(observed) == 3
    assert all(result.success for result in observed)


def main():
    tests = [
        test_build_plan,
        test_safe_plan_validation,
        test_experimental_plan_rejected,
        test_documented_write_rejected,
        test_probe_success,
        test_discovery_success,
        test_discovery_records_failure,
        test_probe_callback,
    ]

    for test in tests:
        test()
        print(f"PASS: {test.__name__}")

    print()
    print("Project Stargate Mission 3C.2: PASS")


if __name__ == "__main__":
    main()
