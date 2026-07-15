import pytest

from truepanel.lab.capability_registry import (
    CapabilityEvidence,
    CapabilityRecord,
    CapabilityRegistry,
)


def test_empty_registry():
    registry = CapabilityRegistry()

    assert registry.capabilities() == []


def test_unknown_capability_returns_empty_record():
    registry = CapabilityRegistry()

    record = registry.get("glyph_upload")

    assert record.name == "glyph_upload"
    assert record.observed is False
    assert record.confidence == 0.0


def test_record_creates_capability():
    registry = CapabilityRegistry()

    registry.record(
        "glyph_upload",
        CapabilityEvidence(
            source="unit-test",
            confidence=0.5,
        ),
    )

    assert registry.capabilities() == [
        "glyph_upload"
    ]


def test_record_is_observed():
    registry = CapabilityRegistry()

    registry.record(
        "glyph_upload",
        CapabilityEvidence(
            source="unit-test",
            confidence=0.25,
        ),
    )

    record = registry.get("glyph_upload")

    assert record.observed


def test_confidence_is_highest_observation():
    registry = CapabilityRegistry()

    registry.record(
        "glyph_upload",
        CapabilityEvidence(
            source="A",
            confidence=0.20,
        ),
    )

    registry.record(
        "glyph_upload",
        CapabilityEvidence(
            source="B",
            confidence=0.80,
        ),
    )

    assert (
        registry.get("glyph_upload").confidence
        == pytest.approx(0.80)
    )


def test_multiple_capabilities_sorted():
    registry = CapabilityRegistry()

    registry.record(
        "scroll",
        CapabilityEvidence(
            source="A",
            confidence=0.5,
        ),
    )

    registry.record(
        "blink",
        CapabilityEvidence(
            source="A",
            confidence=0.5,
        ),
    )

    registry.record(
        "glyph_upload",
        CapabilityEvidence(
            source="A",
            confidence=0.5,
        ),
    )

    assert registry.capabilities() == [
        "blink",
        "glyph_upload",
        "scroll",
    ]


def test_record_preserves_evidence():
    registry = CapabilityRegistry()

    evidence = CapabilityEvidence(
        source="Discovery",
        confidence=1.0,
        detail="Observed during graphics probe",
    )

    registry.record(
        "glyph_upload",
        evidence,
    )

    record = registry.get("glyph_upload")

    assert len(record.evidence) == 1
    assert record.evidence[0] == evidence


def test_as_dict_contains_evidence():
    registry = CapabilityRegistry()

    registry.record(
        "glyph_upload",
        CapabilityEvidence(
            source="Discovery",
            confidence=1.0,
            detail="verified",
        ),
    )

    payload = registry.as_dict()

    assert "glyph_upload" in payload

    capability = payload["glyph_upload"]

    assert capability["observed"] is True
    assert capability["confidence"] == 1.0
    assert capability["evidence"][0]["source"] == "Discovery"


def test_record_accepts_multiple_observations():
    record = CapabilityRecord("glyph_upload")

    record.add(
        CapabilityEvidence(
            source="A",
            confidence=0.25,
        )
    )

    record.add(
        CapabilityEvidence(
            source="B",
            confidence=0.75,
        )
    )

    assert len(record.evidence) == 2
    assert record.confidence == pytest.approx(0.75)
