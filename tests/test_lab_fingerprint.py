import pytest

from truepanel.lab.fingerprint import (
    CapabilityFingerprint,
    CapabilityState,
    ControllerFingerprint,
    FingerprintEvidence,
    build_a125_baseline_fingerprint,
)


def test_evidence_confidence_uses_sample_ratio():
    evidence = FingerprintEvidence(
        source="repeat",
        observation="board response",
        successful_samples=99,
        total_samples=100,
    )

    assert evidence.confidence == pytest.approx(0.99)


def test_evidence_rejects_impossible_sample_counts():
    with pytest.raises(ValueError):
        FingerprintEvidence(
            source="repeat",
            observation="invalid result",
            successful_samples=2,
            total_samples=1,
        )


def test_capability_names_are_normalized():
    capability = CapabilityFingerprint(
        name="Custom Glyph Support",
        state=CapabilityState.EXPERIMENTAL,
    )

    assert capability.name == "custom_glyph_support"
    assert capability.state is CapabilityState.EXPERIMENTAL


def test_capability_confidence_is_weighted_by_samples():
    capability = CapabilityFingerprint(
        name="board_query",
        state=CapabilityState.SUPPORTED,
        evidence=[
            FingerprintEvidence(
                source="capture-a",
                observation="response",
                successful_samples=10,
                total_samples=10,
            ),
            FingerprintEvidence(
                source="capture-b",
                observation="response",
                successful_samples=5,
                total_samples=10,
            ),
        ],
    )

    assert capability.confidence == pytest.approx(0.75)


def test_controller_fingerprint_reports_geometry():
    fingerprint = ControllerFingerprint(
        controller_family="A125",
        display_columns=16,
        display_rows=2,
    )

    assert fingerprint.geometry == "16x2"
    assert fingerprint.to_dict()["display"]["geometry"] == "16x2"


def test_controller_confidence_includes_capability_evidence():
    fingerprint = ControllerFingerprint(controller_family="A125")

    fingerprint.add_evidence(
        FingerprintEvidence(
            source="identity",
            observation="board identified",
            successful_samples=25,
            total_samples=25,
        )
    )
    fingerprint.record_capability(
        name="version_query",
        state=CapabilityState.SUPPORTED,
        evidence=[
            FingerprintEvidence(
                source="repeat",
                observation="version response",
                successful_samples=24,
                total_samples=25,
            )
        ],
    )

    assert fingerprint.confidence == pytest.approx(49 / 50)


def test_record_capability_replaces_same_normalized_name():
    fingerprint = ControllerFingerprint(controller_family="A125")

    fingerprint.record_capability(
        "Backlight Control",
        CapabilityState.EXPERIMENTAL,
    )
    fingerprint.record_capability(
        "backlight_control",
        CapabilityState.SUPPORTED,
    )

    assert len(fingerprint.capabilities) == 1
    assert (
        fingerprint.capabilities["backlight_control"].state
        is CapabilityState.SUPPORTED
    )


def test_serialized_capabilities_are_sorted():
    fingerprint = ControllerFingerprint(controller_family="A125")

    fingerprint.record_capability(
        "version_query",
        CapabilityState.SUPPORTED,
    )
    fingerprint.record_capability(
        "board_query",
        CapabilityState.SUPPORTED,
    )

    assert list(fingerprint.to_dict()["capabilities"]) == [
        "board_query",
        "version_query",
    ]


def test_a125_baseline_contains_known_transport_profile():
    fingerprint = build_a125_baseline_fingerprint()
    payload = fingerprint.to_dict()

    assert fingerprint.controller_family == "A125"
    assert payload["transport"] == {
        "serial_port": "/dev/ttyS1",
        "baud_rate": 1200,
        "protocol_preamble": 0x4D,
    }
    assert payload["capabilities"]["board_query"]["state"] == "supported"
    assert payload["capabilities"]["version_query"]["state"] == "supported"
    assert payload["capabilities"]["button_query"]["state"] == "supported"


def test_controller_rejects_invalid_preamble():
    with pytest.raises(ValueError):
        ControllerFingerprint(
            controller_family="A125",
            protocol_preamble=0x100,
        )
