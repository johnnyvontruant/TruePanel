import pytest

from truepanel.lab.a125_capabilities import (
    A125IdentityCapabilityProvider,
    build_a125_read_only_providers,
)
from truepanel.lab.capabilities import (
    CapabilityProviderDetector,
    CapabilityProviderRegistry,
    ProbeOutcome,
    ProbeSafety,
    provider_report_to_observations,
)
from truepanel.lab.fingerprint import CapabilityState
from truepanel.lab.fingerprint_builder import (
    FingerprintBuilder,
    StaticFingerprintProvider,
)


class FakeController:
    def __init__(
        self,
        *,
        board_id=0x007D,
        protocol_version=0x0003,
        buttons=0x0000,
    ):
        self.board_id = board_id
        self.protocol_version = protocol_version
        self.buttons = buttons
        self.calls = []

    def query_board_id(self):
        self.calls.append("board")
        return self.board_id

    def query_protocol_version(self):
        self.calls.append("version")
        return self.protocol_version

    def query_buttons(self):
        self.calls.append("buttons")
        return self.buttons


def detect(controller):
    provider = A125IdentityCapabilityProvider(controller)
    registry = CapabilityProviderRegistry([provider])

    return CapabilityProviderDetector(registry).detect()


def test_a125_identity_provider_metadata():
    provider = A125IdentityCapabilityProvider(FakeController())

    assert provider.name == "a125_identity"
    assert provider.category == "controller"
    assert len(tuple(provider.probes())) == 3


def test_a125_identity_provider_uses_read_only_safety():
    provider = A125IdentityCapabilityProvider(FakeController())

    assert {
        probe.safety
        for probe in provider.probes()
    } == {
        ProbeSafety.DOCUMENTED_READ_ONLY,
    }


def test_a125_identity_provider_executes_documented_queries():
    controller = FakeController()

    report = detect(controller)

    assert report.healthy is True
    assert report.supported == 3
    assert controller.calls == [
        "board",
        "buttons",
        "version",
    ]


def test_a125_identity_results_contain_values_and_opcodes():
    report = detect(FakeController())
    results = {
        result.capability: result
        for result in report.results
    }

    board = results["board_query"]
    version = results["version_query"]
    buttons = results["button_query"]

    assert board.outcome is ProbeOutcome.SUPPORTED
    assert board.metadata["opcode_hex"] == "0x00"
    assert board.metadata["value_hex"] == "0x007D"

    assert version.metadata["opcode_hex"] == "0x07"
    assert version.metadata["value_hex"] == "0x0003"

    assert buttons.metadata["opcode_hex"] == "0x06"
    assert buttons.metadata["value_hex"] == "0x0000"


def test_a125_identity_results_include_latency():
    report = detect(FakeController())

    for result in report.results:
        assert result.metadata["latency_ms"] >= 0
        assert " ms" in result.detail


def test_a125_identity_provider_rejects_invalid_value():
    controller = FakeController(board_id=0x10000)

    report = detect(controller)
    results = {
        result.capability: result
        for result in report.results
    }

    assert report.healthy is False
    assert results["board_query"].outcome is ProbeOutcome.ERROR
    assert "outside 16 bits" in results["board_query"].detail


def test_a125_identity_provider_continues_after_query_failure():
    class PartiallyBrokenController(FakeController):
        def query_protocol_version(self):
            self.calls.append("version")
            raise TimeoutError("version query timed out")

    controller = PartiallyBrokenController()
    report = detect(controller)
    results = {
        result.capability: result
        for result in report.results
    }

    assert report.healthy is False
    assert report.supported == 2
    assert report.inconclusive == 1
    assert results["version_query"].outcome is ProbeOutcome.ERROR
    assert results["board_query"].outcome is ProbeOutcome.SUPPORTED
    assert results["button_query"].outcome is ProbeOutcome.SUPPORTED


def test_a125_identity_observations_enrich_fingerprint():
    report = detect(FakeController())

    fingerprint_provider = StaticFingerprintProvider(
        name="a125-capabilities",
        items=list(
            provider_report_to_observations(report)
        ),
    )

    fingerprint = FingerprintBuilder().build(
        [fingerprint_provider]
    )

    for name in (
        "board_query",
        "version_query",
        "button_query",
    ):
        capability = fingerprint.capabilities[name]

        assert capability.state is CapabilityState.SUPPORTED
        assert capability.confidence == pytest.approx(1.0)
        assert (
            capability.evidence[-1].source
            == "capability-provider:a125_identity"
        )


def test_build_a125_read_only_providers():
    providers = build_a125_read_only_providers(
        FakeController()
    )

    assert len(providers) == 1
    assert providers[0].name == "a125_identity"


def test_provider_report_serializes_hardware_evidence():
    payload = detect(FakeController()).as_dict()

    assert payload["healthy"] is True
    assert payload["provider_count"] == 1
    assert payload["result_count"] == 3

    results = payload["providers"][0]["report"]["results"]

    assert {
        result["capability"]
        for result in results
    } == {
        "board_query",
        "version_query",
        "button_query",
    }
    assert all(
        result["metadata"]["safety"]
        == "documented_read_only"
        for result in results
    )
