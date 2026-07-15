import pytest

from truepanel.lab.capabilities import (
    CapabilityDetectionReport,
    CapabilityDetector,
    CapabilityProbe,
    CapabilityProbeResult,
    CapabilityRegistry,
    ProbeOutcome,
    ProbeSafety,
    report_to_observations,
    result_to_observation,
)
from truepanel.lab.fingerprint import CapabilityState


def make_probe(
    *,
    name="board-query",
    capability="board_query",
    safety=ProbeSafety.DOCUMENTED_READ_ONLY,
    outcome=ProbeOutcome.SUPPORTED,
):
    return CapabilityProbe(
        name=name,
        capability=capability,
        safety=safety,
        execute=lambda: CapabilityProbeResult(
            capability=capability,
            outcome=outcome,
            detail=f"{capability} probe completed",
        ),
    )


def test_probe_names_are_normalized():
    probe = make_probe(
        name="Board Query",
        capability="Board Query",
    )

    assert probe.name == "board_query"
    assert probe.capability == "board_query"


def test_probe_result_names_are_normalized():
    result = CapabilityProbeResult(
        capability="Custom Glyphs",
        outcome=ProbeOutcome.EXPERIMENTAL,
        detail="Partial glyph response observed",
    )

    assert result.capability == "custom_glyphs"


def test_probe_result_confidence_uses_sample_ratio():
    result = CapabilityProbeResult(
        capability="board_query",
        outcome=ProbeOutcome.SUPPORTED,
        detail="Repeated board query",
        successful_samples=24,
        total_samples=25,
    )

    assert result.confidence == pytest.approx(0.96)


def test_probe_result_rejects_invalid_samples():
    with pytest.raises(ValueError):
        CapabilityProbeResult(
            capability="board_query",
            outcome=ProbeOutcome.SUPPORTED,
            detail="Invalid",
            successful_samples=2,
            total_samples=1,
        )


def test_registry_rejects_duplicate_probe_names():
    probe = make_probe()
    registry = CapabilityRegistry([probe])

    with pytest.raises(ValueError):
        registry.register(probe)


def test_registry_returns_sorted_probes():
    registry = CapabilityRegistry(
        [
            make_probe(
                name="version",
                capability="version_query",
            ),
            make_probe(
                name="board",
                capability="board_query",
            ),
        ]
    )

    assert [probe.name for probe in registry.all()] == [
        "board",
        "version",
    ]


def test_detector_runs_allowed_probes():
    registry = CapabilityRegistry([make_probe()])
    detector = CapabilityDetector(registry)

    report = detector.detect()

    assert report.healthy is True
    assert report.supported == 1
    assert report.unsupported == 0
    assert len(report.results) == 1


def test_detector_blocks_unapproved_safety_class():
    registry = CapabilityRegistry(
        [
            make_probe(
                safety=ProbeSafety.DOCUMENTED_STATEFUL,
            )
        ]
    )
    detector = CapabilityDetector(registry)

    with pytest.raises(PermissionError):
        detector.detect()


def test_detector_allows_explicit_safety_authorization():
    registry = CapabilityRegistry(
        [
            make_probe(
                safety=ProbeSafety.DOCUMENTED_STATEFUL,
            )
        ]
    )
    detector = CapabilityDetector(registry)

    report = detector.detect(
        allowed_safety=[
            ProbeSafety.DOCUMENTED_STATEFUL,
        ]
    )

    assert report.supported == 1


def test_detector_converts_probe_exception_to_error_result():
    probe = CapabilityProbe(
        name="broken",
        capability="graphics",
        safety=ProbeSafety.PASSIVE,
        execute=lambda: (_ for _ in ()).throw(
            RuntimeError("probe failed")
        ),
    )
    detector = CapabilityDetector(
        CapabilityRegistry([probe])
    )

    report = detector.detect()

    assert report.healthy is False
    assert report.inconclusive == 1
    assert report.results[0].outcome is ProbeOutcome.ERROR
    assert report.results[0].successful_samples == 0


def test_detector_rejects_wrong_returned_capability():
    probe = CapabilityProbe(
        name="wrong",
        capability="board_query",
        safety=ProbeSafety.PASSIVE,
        execute=lambda: CapabilityProbeResult(
            capability="version_query",
            outcome=ProbeOutcome.SUPPORTED,
            detail="Wrong capability returned",
        ),
    )

    detector = CapabilityDetector(
        CapabilityRegistry([probe])
    )

    with pytest.raises(ValueError):
        detector.detect()


@pytest.mark.parametrize(
    ("outcome", "expected_state"),
    [
        (
            ProbeOutcome.SUPPORTED,
            CapabilityState.SUPPORTED,
        ),
        (
            ProbeOutcome.UNSUPPORTED,
            CapabilityState.UNSUPPORTED,
        ),
        (
            ProbeOutcome.EXPERIMENTAL,
            CapabilityState.EXPERIMENTAL,
        ),
        (
            ProbeOutcome.INCONCLUSIVE,
            CapabilityState.UNKNOWN,
        ),
        (
            ProbeOutcome.ERROR,
            CapabilityState.UNKNOWN,
        ),
    ],
)
def test_result_to_observation_maps_states(
    outcome,
    expected_state,
):
    result = CapabilityProbeResult(
        capability="graphics",
        outcome=outcome,
        detail="Graphics probe result",
        successful_samples=1,
        total_samples=1,
    )

    observation = result_to_observation(result)

    assert observation.name == "graphics"
    assert observation.state is expected_state
    assert observation.evidence[0].source == "capability-detector"


def test_report_counts_all_outcome_types():
    report = CapabilityDetectionReport(
        results=[
            CapabilityProbeResult(
                capability="one",
                outcome=ProbeOutcome.SUPPORTED,
                detail="one",
            ),
            CapabilityProbeResult(
                capability="two",
                outcome=ProbeOutcome.UNSUPPORTED,
                detail="two",
            ),
            CapabilityProbeResult(
                capability="three",
                outcome=ProbeOutcome.EXPERIMENTAL,
                detail="three",
            ),
            CapabilityProbeResult(
                capability="four",
                outcome=ProbeOutcome.INCONCLUSIVE,
                detail="four",
            ),
            CapabilityProbeResult(
                capability="five",
                outcome=ProbeOutcome.ERROR,
                detail="five",
                successful_samples=0,
            ),
        ]
    )

    assert report.supported == 1
    assert report.unsupported == 1
    assert report.experimental == 1
    assert report.inconclusive == 2
    assert report.healthy is False


def test_report_to_observations_preserves_order():
    report = CapabilityDetectionReport(
        results=[
            CapabilityProbeResult(
                capability="board_query",
                outcome=ProbeOutcome.SUPPORTED,
                detail="Board supported",
            ),
            CapabilityProbeResult(
                capability="graphics",
                outcome=ProbeOutcome.INCONCLUSIVE,
                detail="Graphics unknown",
                successful_samples=0,
            ),
        ]
    )

    observations = report_to_observations(
        report,
        source="unit-test",
    )

    assert [item.name for item in observations] == [
        "board_query",
        "graphics",
    ]
    assert observations[0].evidence[0].source == "unit-test"


def test_report_serialization():
    report = CapabilityDetectionReport(
        results=[
            CapabilityProbeResult(
                capability="board_query",
                outcome=ProbeOutcome.SUPPORTED,
                detail="Board query responded",
                metadata={"opcode": "0x00"},
            )
        ]
    )

    payload = report.as_dict()

    assert payload["healthy"] is True
    assert payload["total"] == 1
    assert payload["supported"] == 1
    assert payload["results"][0]["capability"] == "board_query"
    assert payload["results"][0]["metadata"]["opcode"] == "0x00"
