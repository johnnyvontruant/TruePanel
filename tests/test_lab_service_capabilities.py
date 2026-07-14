from truepanel.lab.service import LaboratoryService


class FakeController:
    def query_board_id(self):
        return 0x007D

    def query_protocol_version(self):
        return 0x0003

    def query_buttons(self):
        return 0x0000


def test_service_builds_baseline_capability_report():
    report = (
        LaboratoryService()
        .build_baseline_capability_report()
    )

    assert report.healthy is True
    assert report.supported == 3
    assert len(report.results) == 3
    assert report.providers[0].provider == "a125_baseline"


def test_baseline_capabilities_have_zero_confidence():
    report = (
        LaboratoryService()
        .build_baseline_capability_report()
    )

    assert all(
        result.confidence == 0.0
        for result in report.results
    )


def test_service_detects_live_a125_capabilities():
    report = LaboratoryService().detect_capabilities(
        FakeController()
    )

    assert report.healthy is True
    assert report.supported == 3
    assert {
        result.capability
        for result in report.results
    } == {
        "board_query",
        "version_query",
        "button_query",
    }
