import pytest

from truepanel.lab.protocol import (
    PROTOCOL_ARMING_PHRASE,
    ProtocolAuthorization,
    ProtocolExperiment,
    ProtocolExperimentValidator,
    ProtocolHypothesis,
    ProtocolLiveRunner,
    ProtocolPolicy,
    ProtocolSequence,
    ProtocolStep,
    RunState,
)
from truepanel.lab.protocol.experiment import (
    ExperimentRisk,
)
from truepanel.lab.protocol.sequence import (
    StepOperation,
)


class FakeController:
    def __init__(
        self,
        *,
        fail_on=None,
    ):
        self.sent = []
        self.fail_on = fail_on

    def send(self, payload):
        payload = bytes(payload)

        if payload == self.fail_on:
            raise RuntimeError(
                "intentional transport failure"
            )

        self.sent.append(payload)
        return payload


def hypothesis():
    return ProtocolHypothesis(
        title="Display-only candidate",
        statement=(
            "The candidate sequence may alter display behavior."
        ),
        expected_observation=(
            "The selected display cell visibly changes."
        ),
        rejection_condition=(
            "The selected display cell does not change."
        ),
    )


def display_experiment(
    *,
    packet=b"\x4D\x0C\x00\x01\xFF",
    repeat_count=1,
):
    return ProtocolExperiment(
        name="display-test",
        hypothesis=hypothesis(),
        sequence=ProtocolSequence.from_steps(
            (
                ProtocolStep(
                    operation=StepOperation.TRANSMIT,
                    payload=packet,
                ),
                ProtocolStep(
                    operation=(
                        StepOperation.DISPLAY_VERIFY
                    ),
                ),
                ProtocolStep(
                    operation=StepOperation.RESTORE,
                    payload=b"\x4D\x0D",
                ),
            )
        ),
        risk=ExperimentRisk.DISPLAY_ONLY,
        repeat_count=repeat_count,
    )


def authorize(experiment):
    return ProtocolAuthorization.issue(
        experiment.experiment_id,
        PROTOCOL_ARMING_PHRASE,
    )


def test_validator_allows_documented_display_write():
    experiment = display_experiment()

    result = ProtocolExperimentValidator().validate(
        experiment
    )

    assert result.valid is True


def test_validator_denies_unknown_opcode_by_default():
    experiment = display_experiment(
        packet=b"\x4D\x10\x00",
    )

    result = ProtocolExperimentValidator().validate(
        experiment
    )

    assert result.valid is False
    assert result.reason.value == (
        "opcode_not_approved"
    )


def test_validator_allows_explicit_experimental_opcode():
    experiment = display_experiment(
        packet=b"\x4D\x10\x00",
    )

    validator = ProtocolExperimentValidator(
        ProtocolPolicy(
            experimental_opcodes=frozenset(
                {0x10}
            )
        )
    )

    assert validator.validate(
        experiment
    ).valid is True


def test_validator_denies_reset_even_if_requested():
    experiment = display_experiment(
        packet=b"\x4D\xFF",
    )

    result = ProtocolExperimentValidator().validate(
        experiment
    )

    assert result.valid is False
    assert result.reason.value == (
        "forbidden_opcode"
    )


def test_policy_rejects_reset_allowlist():
    with pytest.raises(
        ValueError,
        match="forbidden opcode",
    ):
        ProtocolPolicy(
            experimental_opcodes=frozenset(
                {0xFF}
            )
        )


def test_validator_requires_final_restore():
    experiment = ProtocolExperiment(
        name="bad-restore-order",
        hypothesis=hypothesis(),
        sequence=ProtocolSequence.from_steps(
            (
                ProtocolStep(
                    operation=StepOperation.RESTORE,
                    payload=b"\x4D\x0D",
                ),
                ProtocolStep(
                    operation=StepOperation.TRANSMIT,
                    payload=b"\x4D\x0C\x00\x01\xFF",
                ),
            )
        ),
        risk=ExperimentRisk.DISPLAY_ONLY,
    )

    result = ProtocolExperimentValidator().validate(
        experiment
    )

    assert result.valid is False
    assert result.reason.value == (
        "restore_not_final"
    )


def test_exact_arming_phrase_required():
    experiment = display_experiment()

    with pytest.raises(
        PermissionError,
        match="Exact protocol arming phrase",
    ):
        ProtocolAuthorization.issue(
            experiment.experiment_id,
            "close enough",
        )


def test_authorization_is_one_time():
    experiment = display_experiment()
    authorization = authorize(
        experiment
    )

    authorization.consume(
        experiment.experiment_id
    )

    with pytest.raises(
        PermissionError,
        match="invalid, expired, consumed",
    ):
        authorization.consume(
            experiment.experiment_id
        )


def test_live_runner_sends_and_restores():
    controller = FakeController()
    experiment = display_experiment()

    run = ProtocolLiveRunner(
        controller
    ).run(
        experiment,
        authorize(experiment),
    )

    assert run.state is RunState.COMPLETED
    assert run.simulation is False
    assert controller.sent == [
        b"\x4D\x0C\x00\x01\xFF",
        b"\x4D\x0D",
    ]
    assert run.observations[0].restored is True


def test_live_runner_restores_after_failure():
    packet = b"\x4D\x0C\x00\x01\xFF"

    controller = FakeController(
        fail_on=packet
    )
    experiment = display_experiment(
        packet=packet
    )

    run = ProtocolLiveRunner(
        controller
    ).run(
        experiment,
        authorize(experiment),
    )

    assert run.state is RunState.FAILED
    assert controller.sent == [
        b"\x4D\x0D",
    ]
    assert "intentional transport failure" in (
        run.error
    )


def test_live_runner_rejects_unapproved_experiment():
    controller = FakeController()
    experiment = display_experiment(
        packet=b"\x4D\x10\x00",
    )

    with pytest.raises(
        PermissionError,
        match="not approved",
    ):
        ProtocolLiveRunner(
            controller
        ).run(
            experiment,
            authorize(experiment),
        )

    assert controller.sent == []


def test_live_runner_accepts_session_allowlist():
    controller = FakeController()
    experiment = display_experiment(
        packet=b"\x4D\x10\x00",
    )

    validator = ProtocolExperimentValidator(
        ProtocolPolicy(
            experimental_opcodes=frozenset(
                {0x10}
            )
        )
    )

    run = ProtocolLiveRunner(
        controller,
        validator=validator,
    ).run(
        experiment,
        authorize(experiment),
    )

    assert run.state is RunState.COMPLETED
    assert controller.sent == [
        b"\x4D\x10\x00",
        b"\x4D\x0D",
    ]
