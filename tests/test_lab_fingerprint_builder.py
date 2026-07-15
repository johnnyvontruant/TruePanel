import pytest

from truepanel.lab.fingerprint import (
    CapabilityState,
    ControllerFingerprint,
    FingerprintEvidence,
)
from truepanel.lab.fingerprint_builder import (
    CapabilityObservation,
    DisplayObservation,
    FingerprintBuilder,
    IdentityObservation,
    MetadataObservation,
    StaticFingerprintProvider,
    TimingObservation,
    build_live_a125_fingerprint,
)


def test_builder_uses_a125_baseline_by_default():
    fingerprint = FingerprintBuilder().build()

    assert fingerprint.controller_family == "A125"
    assert fingerprint.serial_port == "/dev/ttyS1"
    assert fingerprint.baud_rate == 1200
    assert fingerprint.protocol_preamble == 0x4D


def test_identity_provider_sets_board_and_firmware():
    provider = StaticFingerprintProvider(
        name="identity",
        items=[
            IdentityObservation(
                board_id="0x007D",
                firmware_version="1.2.3",
            )
        ],
    )

    fingerprint = FingerprintBuilder().build([provider])

    assert fingerprint.board_id == "0x007D"
    assert fingerprint.firmware_version == "1.2.3"


def test_display_provider_sets_geometry():
    provider = StaticFingerprintProvider(
        name="display",
        items=[
            DisplayObservation(
                columns=16,
                rows=2,
            )
        ],
    )

    fingerprint = FingerprintBuilder().build([provider])

    assert fingerprint.geometry == "16x2"


def test_timing_provider_sets_latency_and_evidence():
    provider = StaticFingerprintProvider(
        name="repeatability",
        items=[
            TimingObservation(
                average_latency_ms=50.48,
                successful_samples=100,
                total_samples=100,
            )
        ],
    )

    fingerprint = FingerprintBuilder().build([provider])

    assert fingerprint.average_latency_ms == pytest.approx(50.48)
    assert fingerprint.confidence == pytest.approx(1.0)
    assert fingerprint.evidence[-1].source == "latency"


def test_capability_provider_enriches_existing_baseline_capability():
    evidence = FingerprintEvidence(
        source="repeat",
        observation="board query repeated successfully",
        successful_samples=25,
        total_samples=25,
    )
    provider = StaticFingerprintProvider(
        name="capabilities",
        items=[
            CapabilityObservation(
                name="board_query",
                state=CapabilityState.SUPPORTED,
                evidence=(evidence,),
                notes="Live verification complete.",
            )
        ],
    )

    fingerprint = FingerprintBuilder().build([provider])
    capability = fingerprint.capabilities["board_query"]

    assert capability.state is CapabilityState.SUPPORTED
    assert capability.confidence == pytest.approx(1.0)
    assert capability.notes == "Live verification complete."


def test_metadata_provider_merges_values():
    provider = StaticFingerprintProvider(
        name="metadata",
        items=[
            MetadataObservation(
                values={
                    "capture_file": "sample.log",
                    "query_count": 100,
                }
            )
        ],
    )

    fingerprint = FingerprintBuilder().build([provider])

    assert fingerprint.metadata["capture_file"] == "sample.log"
    assert fingerprint.metadata["query_count"] == 100
    assert fingerprint.metadata["project"] == "Project Stargate"


def test_later_provider_observation_wins_for_identity():
    first = StaticFingerprintProvider(
        name="first",
        items=[IdentityObservation(board_id="0x0001")],
    )
    second = StaticFingerprintProvider(
        name="second",
        items=[IdentityObservation(board_id="0x007D")],
    )

    fingerprint = FingerprintBuilder().build([first, second])

    assert fingerprint.board_id == "0x007D"


def test_builder_does_not_mutate_custom_baseline():
    baseline = ControllerFingerprint(
        controller_family="TEST",
        board_id="original",
    )
    provider = StaticFingerprintProvider(
        name="identity",
        items=[IdentityObservation(board_id="updated")],
    )

    fingerprint = FingerprintBuilder(baseline).build([provider])

    assert fingerprint.board_id == "updated"
    assert baseline.board_id == "original"


def test_builder_rejects_invalid_provider():
    with pytest.raises(TypeError):
        FingerprintBuilder().build([object()])


def test_builder_rejects_unsupported_observation():
    provider = StaticFingerprintProvider(
        name="broken",
        items=["not-an-observation"],  # type: ignore[list-item]
    )

    with pytest.raises(TypeError):
        FingerprintBuilder().build([provider])


def test_live_a125_builder_assembles_common_results():
    fingerprint = build_live_a125_fingerprint(
        board_id="0x007D",
        firmware_version="1.0",
        average_latency_ms=50.48,
        successful_samples=100,
        total_samples=100,
    )

    payload = fingerprint.to_dict()

    assert payload["board_id"] == "0x007D"
    assert payload["firmware_version"] == "1.0"
    assert payload["timing"]["average_latency_ms"] == pytest.approx(50.48)
    assert payload["confidence"] == pytest.approx(1.0)


def test_live_builder_requires_samples_with_latency():
    with pytest.raises(ValueError):
        build_live_a125_fingerprint(
            average_latency_ms=50.48,
        )


def test_timing_observation_rejects_invalid_samples():
    with pytest.raises(ValueError):
        TimingObservation(
            average_latency_ms=50.0,
            successful_samples=11,
            total_samples=10,
        )


def test_display_observation_rejects_invalid_geometry_during_build():
    provider = StaticFingerprintProvider(
        name="display",
        items=[DisplayObservation(columns=0, rows=2)],
    )

    with pytest.raises(ValueError):
        FingerprintBuilder().build([provider])
