import json

import pytest

from truepanel.lab.protocol import (
    EvidenceConfidence,
    EvidenceRecord,
    EvidenceVerdict,
    ObservationOutcome,
    ProtocolExperiment,
    ProtocolHypothesis,
    ProtocolObservation,
    ProtocolSequence,
    ProtocolStep,
)
from truepanel.lab.protocol.experiment import (
    ExperimentRisk,
)
from truepanel.lab.protocol.sequence import (
    StepOperation,
)


def restore_step():
    return ProtocolStep(
        operation=StepOperation.RESTORE,
        payload=b"\x4D\x0D",
        description="Clear display",
    )


def safe_sequence():
    return ProtocolSequence.from_steps(
        (
            ProtocolStep(
                operation=StepOperation.TRANSMIT,
                payload=b"\x4D\x0C\x00\x01\xFF",
                description="Display candidate byte",
            ),
            ProtocolStep(
                operation=StepOperation.DISPLAY_VERIFY,
                description="Inspect visible LCD state",
            ),
            restore_step(),
        )
    )


def hypothesis():
    return ProtocolHypothesis(
        title="Candidate glyph behavior",
        statement=(
            "The candidate sequence changes one display glyph."
        ),
        expected_observation=(
            "A stable new glyph appears in the selected position."
        ),
        rejection_condition=(
            "No visible change occurs."
        ),
    )


def experiment():
    return ProtocolExperiment(
        name="candidate-glyph-test",
        hypothesis=hypothesis(),
        sequence=safe_sequence(),
        risk=ExperimentRisk.DISPLAY_ONLY,
        repeat_count=3,
    )


def test_transmit_step_requires_payload():
    with pytest.raises(
        ValueError,
        match="cannot be empty",
    ):
        ProtocolStep(
            operation=StepOperation.TRANSMIT,
        )


def test_delay_requires_positive_duration():
    with pytest.raises(
        ValueError,
        match="positive delay",
    ):
        ProtocolStep(
            operation=StepOperation.DELAY,
            delay_seconds=0,
        )


def test_verify_step_rejects_payload():
    with pytest.raises(
        ValueError,
        match="cannot carry payload",
    ):
        ProtocolStep(
            operation=StepOperation.DISPLAY_VERIFY,
            payload=b"\x01",
        )


def test_sequence_requires_steps():
    with pytest.raises(
        ValueError,
        match="at least one step",
    ):
        ProtocolSequence(())


def test_sequence_reports_restore():
    sequence = safe_sequence()

    assert len(sequence) == 3
    assert sequence.transmit_count == 1
    assert sequence.has_restore is True


def test_experiment_requires_restore_when_requested():
    sequence = ProtocolSequence.from_steps(
        (
            ProtocolStep(
                operation=StepOperation.TRANSMIT,
                payload=b"\x4D\x0C",
            ),
        )
    )

    with pytest.raises(
        ValueError,
        match="require a restore step",
    ):
        ProtocolExperiment(
            name="unsafe",
            hypothesis=hypothesis(),
            sequence=sequence,
            risk=ExperimentRisk.DISPLAY_ONLY,
            requires_restoration=True,
        )


def test_forbidden_experiment_cannot_be_constructed():
    with pytest.raises(
        ValueError,
        match="cannot be constructed",
    ):
        ProtocolExperiment(
            name="forbidden",
            hypothesis=hypothesis(),
            sequence=safe_sequence(),
            risk=ExperimentRisk.FORBIDDEN,
        )


def test_experiment_serializes():
    payload = experiment().as_dict()

    assert payload["name"] == (
        "candidate-glyph-test"
    )
    assert payload["risk"] == "display_only"
    assert payload["sequence"]["has_restore"] is True

    json.dumps(payload)


def observation(
    experiment_id,
    outcome,
    *,
    repeat_index=1,
):
    return ProtocolObservation(
        experiment_id=experiment_id,
        outcome=outcome,
        visible_effect="Candidate glyph changed",
        response_bytes=b"\x53\xFA",
        duration_ms=12.5,
        repeat_index=repeat_index,
        restored=True,
    )


def test_observation_serializes_response_bytes():
    item = observation(
        "abc",
        ObservationOutcome.CONFIRMED,
    )

    payload = item.as_dict()

    assert payload["response_hex"] == "53 FA"
    assert payload["restored"] is True

    json.dumps(payload)


def test_supported_evidence_low_confidence():
    record = EvidenceRecord(
        "abc",
        (
            observation(
                "abc",
                ObservationOutcome.CONFIRMED,
            ),
        ),
    )

    assert record.verdict is EvidenceVerdict.SUPPORTED
    assert record.confidence is EvidenceConfidence.LOW


def test_supported_evidence_medium_confidence():
    observations = tuple(
        observation(
            "abc",
            ObservationOutcome.CONFIRMED,
            repeat_index=index,
        )
        for index in range(1, 4)
    )

    record = EvidenceRecord(
        "abc",
        observations,
    )

    assert record.verdict is EvidenceVerdict.SUPPORTED
    assert record.confidence is EvidenceConfidence.MEDIUM


def test_supported_evidence_high_confidence():
    observations = tuple(
        observation(
            "abc",
            ObservationOutcome.CONFIRMED,
            repeat_index=index,
        )
        for index in range(1, 11)
    )

    record = EvidenceRecord(
        "abc",
        observations,
    )

    assert record.confidence is EvidenceConfidence.HIGH


def test_mixed_evidence_remains_unknown():
    record = EvidenceRecord(
        "abc",
        (
            observation(
                "abc",
                ObservationOutcome.CONFIRMED,
            ),
            observation(
                "abc",
                ObservationOutcome.REJECTED,
                repeat_index=2,
            ),
        ),
    )

    assert record.verdict is EvidenceVerdict.UNKNOWN
    assert record.confidence is EvidenceConfidence.NONE


def test_evidence_rejects_foreign_observation():
    with pytest.raises(
        ValueError,
        match="another experiment",
    ):
        EvidenceRecord(
            "abc",
            (
                observation(
                    "different",
                    ObservationOutcome.CONFIRMED,
                ),
            ),
        )
