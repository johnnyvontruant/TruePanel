import pytest

from truepanel.lab.service import LaboratoryService


class FakeController:
    def __init__(self):
        self.calls = []

    def query_board_id(self):
        self.calls.append("board")
        return 0x007D

    def query_protocol_version(self):
        self.calls.append("version")
        return 0x0003

    def query_buttons(self):
        self.calls.append("buttons")
        return 0x0000


def test_service_builds_live_fingerprint_from_capabilities():
    controller = FakeController()

    fingerprint, report = (
        LaboratoryService().build_live_fingerprint(
            controller,
            capture_path="capture.log",
        )
    )

    assert fingerprint.board_id == "0x007D"
    assert fingerprint.firmware_version == "0x0003"
    assert fingerprint.average_latency_ms is not None
    assert fingerprint.confidence == pytest.approx(1.0)

    assert report.healthy is True
    assert report.supported == 3


def test_live_fingerprint_queries_each_capability_once():
    controller = FakeController()

    LaboratoryService().build_live_fingerprint(controller)

    assert controller.calls == [
        "board",
        "buttons",
        "version",
    ]


def test_live_fingerprint_uses_provider_evidence():
    fingerprint, _ = (
        LaboratoryService().build_live_fingerprint(
            FakeController()
        )
    )

    for name in (
        "board_query",
        "version_query",
        "button_query",
    ):
        capability = fingerprint.capabilities[name]

        assert capability.confidence == pytest.approx(1.0)
        assert (
            capability.evidence[-1].source
            == "capability-provider:a125_identity"
        )


def test_live_fingerprint_records_pipeline_metadata():
    fingerprint, _ = (
        LaboratoryService().build_live_fingerprint(
            FakeController(),
            capture_path="development/logs/live.log",
        )
    )

    metadata = fingerprint.metadata

    assert metadata["acquisition_mode"] == "live"
    assert metadata["capture_path"].endswith("live.log")
    assert metadata["capability_provider_count"] == 1
    assert metadata["capability_result_count"] == 3
    assert metadata["capability_supported"] == 3
    assert metadata["capability_healthy"] is True


def test_live_fingerprint_latency_is_provider_average():
    fingerprint, report = (
        LaboratoryService().build_live_fingerprint(
            FakeController()
        )
    )

    latencies = [
        result.metadata["latency_ms"]
        for result in report.results
    ]
    expected = sum(latencies) / len(latencies)

    assert fingerprint.average_latency_ms == pytest.approx(
        expected
    )


def test_live_fingerprint_preserves_capability_report():
    fingerprint, report = (
        LaboratoryService().build_live_fingerprint(
            FakeController()
        )
    )

    assert len(report.providers) == 1
    assert report.providers[0].provider == "a125_identity"
    assert {
        result.capability
        for result in report.results
    } == {
        "board_query",
        "version_query",
        "button_query",
    }

    assert fingerprint.controller_family == "A125"
