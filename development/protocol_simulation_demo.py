#!/usr/bin/env python3
"""
Offline Project Stargate protocol-discovery demonstration.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from truepanel.lab.protocol import (
    ProtocolArchive,
    ProtocolExperiment,
    ProtocolHypothesis,
    ProtocolSequence,
    ProtocolSimulationRunner,
    ProtocolStep,
)
from truepanel.lab.protocol.experiment import (
    ExperimentRisk,
)
from truepanel.lab.protocol.sequence import (
    StepOperation,
)


def main():
    experiment = ProtocolExperiment(
        name="cgram-hypothesis-001",
        hypothesis=ProtocolHypothesis(
            title="Candidate custom glyph write",
            statement=(
                "A candidate sequence may program "
                "custom character slot zero."
            ),
            expected_observation=(
                "Displaying byte 0x00 shows the "
                "candidate bitmap."
            ),
            rejection_condition=(
                "Slot zero remains unchanged."
            ),
        ),
        sequence=ProtocolSequence.from_steps(
            (
                ProtocolStep(
                    operation=StepOperation.TRANSMIT,
                    payload=b"\x4D\x10\x00",
                    description=(
                        "Candidate upload prefix"
                    ),
                ),
                ProtocolStep(
                    operation=StepOperation.DELAY,
                    delay_seconds=0.1,
                    description="Controller settling",
                ),
                ProtocolStep(
                    operation=(
                        StepOperation.DISPLAY_VERIFY
                    ),
                    description=(
                        "Inspect custom character slot"
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

    runner = ProtocolSimulationRunner()

    def report(step):
        payload = (
            f" {step.payload_hex}"
            if step.payload
            else ""
        )

        print(
            f"[{step.index}/{step.total}] "
            f"{step.operation.upper()}"
            f"{payload}"
        )

    run = runner.run(
        experiment,
        callback=report,
    )

    archive = ProtocolArchive()
    experiment_path = (
        archive.save_experiment(experiment)
    )
    run_path = archive.save_run(run)

    print()
    print("State      :", run.state.value)
    print("Simulation :", run.simulation)
    print("Steps      :", len(run.steps))
    print(
        "Observations:",
        len(run.observations),
    )
    print("Experiment :", experiment_path)
    print("Run        :", run_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
