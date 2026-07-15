import json

import pytest
from datetime import UTC, datetime
from pathlib import Path

from truepanel.lab.protocol import (
    ProtocolArchive,
    ProtocolExperiment,
    ProtocolHypothesis,
    ProtocolSequence,
    ProtocolSimulationRunner,
    ProtocolStep,
    RunState,
)
from truepanel.lab.protocol.experiment import (
    ExperimentRisk,
)
from truepanel.lab.protocol.sequence import (
    StepOperation,
)


class ManualClock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def experiment():
    return ProtocolExperiment(
        name="cgram-candidate",
        hypothesis=ProtocolHypothesis(
            title="Candidate CGRAM upload",
            statement=(
                "The byte sequence may program "
                "custom character slot zero."
            ),
            expected_observation=(
                "Character byte zero displays "
                "the candidate bitmap."
            ),
            rejection_condition=(
                "Character byte zero remains unchanged."
            ),
        ),
        sequence=ProtocolSequence.from_steps(
            (
                ProtocolStep(
                    operation=StepOperation.TRANSMIT,
                    payload=b"\x4D\x10\x00",
                    description=(
                        "Candidate upload header"
                    ),
                ),
                ProtocolStep(
                    operation=StepOperation.DELAY,
                    delay_seconds=0.1,
                    description=(
                        "Allow controller processing"
                    ),
                ),
                ProtocolStep(
                    operation=(
                        StepOperation.DISPLAY_VERIFY
                    ),
                    description=(
                        "Inspect custom slot zero"
                    ),
                ),
                ProtocolStep(
                    operation=StepOperation.RESTORE,
                    payload=b"\x4D\x0D",
                    description="Clear display",
                ),
            )
        ),
        risk=ExperimentRisk.EXPERIMENTAL_WRITE,
        repeat_count=3,
    )


def test_simulator_completes_without_hardware():
    runner = ProtocolSimulationRunner()

    run = runner.run(
        experiment()
    )

    assert run.state is RunState.COMPLETED
    assert run.simulation is True
    assert len(run.steps) == 4
    assert len(run.observations) == 3
    assert all(
        observation.metadata["simulation"]
        for observation in run.observations
    )


def test_simulator_calls_callback_for_each_step():
    received = []
    runner = ProtocolSimulationRunner()

    run = runner.run(
        experiment(),
        callback=received.append,
    )

    assert run.state is RunState.COMPLETED
    assert len(received) == 4
    assert received[0].operation == "transmit"
    assert received[-1].operation == "restore"


def test_simulator_delay_uses_injected_sleep():
    clock = ManualClock()
    delays = []

    def sleep(seconds):
        delays.append(seconds)
        clock.advance(seconds)

    runner = ProtocolSimulationRunner(
        clock=clock,
        sleep=sleep,
    )

    run = runner.run(
        experiment()
    )

    delay_step = run.steps[1]

    assert delays == [0.1]
    assert delay_step.duration_ms == pytest.approx(100.0)


def test_run_serializes_to_json():
    run = ProtocolSimulationRunner().run(
        experiment()
    )

    payload = run.as_dict()

    assert payload["state"] == "completed"
    assert payload["simulation"] is True
    assert payload["steps"][0][
        "payload_hex"
    ] == "4D 10 00"

    json.dumps(payload)


def test_archive_saves_experiment_and_run(
    tmp_path,
):
    archive = ProtocolArchive(
        tmp_path
    )
    item = experiment()
    run = ProtocolSimulationRunner().run(
        item
    )

    experiment_path = (
        archive.save_experiment(item)
    )
    run_path = archive.save_run(run)

    assert experiment_path.exists()
    assert run_path.exists()

    experiment_payload = archive.load(
        experiment_path
    )
    run_payload = archive.load(
        run_path
    )

    assert (
        experiment_payload["name"]
        == "cgram-candidate"
    )
    assert run_payload["state"] == (
        "completed"
    )


def test_archive_lists_records(
    tmp_path,
):
    archive = ProtocolArchive(
        tmp_path
    )
    item = experiment()
    run = ProtocolSimulationRunner().run(
        item
    )

    archive.save_experiment(item)
    archive.save_run(run)

    assert len(
        archive.list_experiments()
    ) == 1
    assert len(
        archive.list_runs()
    ) == 1


def test_archive_handles_missing_directory(
    tmp_path,
):
    archive = ProtocolArchive(
        tmp_path / "missing"
    )

    assert archive.list_experiments() == ()
    assert archive.list_runs() == ()
