#!/usr/bin/env python3
"""
Guarded A125 CGRAM slot-zero probe.

Hypothesis:
    The documented DISPLAY_WRITE command accepts LCD address 0x40,
    followed by eight CGRAM bitmap rows.

Only opcode 0x0C is transmitted. The display is cleared afterward.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from truepanel.lab.capture import open_controller
from truepanel.lab.protocol import (
    PROTOCOL_ARMING_PHRASE,
    ObservationOutcome,
    ProtocolArchive,
    ProtocolAuthorization,
    ProtocolExperiment,
    ProtocolHypothesis,
    ProtocolLiveRunner,
    ProtocolObservation,
    ProtocolSequence,
    ProtocolStep,
)
from truepanel.lab.protocol.experiment import ExperimentRisk
from truepanel.lab.protocol.sequence import StepOperation


# Highly recognizable alternating checkerboard.
CHECKERBOARD_ROWS = bytes(
    (
        0b10101,
        0b01010,
        0b10101,
        0b01010,
        0b10101,
        0b01010,
        0b10101,
        0b01010,
    )
)

# A125 DISPLAY_WRITE packet:
#   4D 0C <address> <length> <payload>
CGRAM_PACKET = (
    bytes(
        (
            0x4D,
            0x0C,
            0x40,
            len(CHECKERBOARD_ROWS),
        )
    )
    + CHECKERBOARD_ROWS
)

CLEAR_PACKET = b"\x4D\x0D"


def build_experiment():
    return ProtocolExperiment(
        name="cgram-slot0-address-40",
        hypothesis=ProtocolHypothesis(
            title="CGRAM slot-zero address probe",
            statement=(
                "A125 DISPLAY_WRITE address 0x40 may select "
                "HD44780 CGRAM slot zero."
            ),
            expected_observation=(
                "Character byte 0x00 changes into an alternating "
                "checkerboard glyph."
            ),
            rejection_condition=(
                "Character byte 0x00 retains its baseline shape, "
                "the packet is ignored, or the display becomes unstable."
            ),
        ),
        sequence=ProtocolSequence.from_steps(
            (
                ProtocolStep(
                    operation=StepOperation.TRANSMIT,
                    payload=CGRAM_PACKET,
                    description=(
                        "Write checkerboard rows to candidate "
                        "CGRAM address 0x40"
                    ),
                ),
                ProtocolStep(
                    operation=StepOperation.DELAY,
                    delay_seconds=0.2,
                    description="Allow LCD controller processing",
                ),
                ProtocolStep(
                    operation=StepOperation.DISPLAY_VERIFY,
                    description="Display and inspect character slot zero",
                ),
                ProtocolStep(
                    operation=StepOperation.RESTORE,
                    payload=CLEAR_PACKET,
                    description="Clear display",
                ),
            )
        ),
        risk=ExperimentRisk.DISPLAY_ONLY,
        repeat_count=1,
        requires_restoration=True,
    )


def main():
    experiment = build_experiment()

    print("Project Stargate CGRAM Probe")
    print("============================")
    print("Experiment :", experiment.name)
    print("Packet     :", CGRAM_PACKET.hex(" ").upper())
    print("Target     : character slot 0x00")
    print()
    print("Checkerboard preview:")
    print("#.#.#")
    print(".#.#.")
    print("#.#.#")
    print(".#.#.")
    print("#.#.#")
    print(".#.#.")
    print("#.#.#")
    print(".#.#.")
    print()

    phrase = input(
        f'Type exactly "{PROTOCOL_ARMING_PHRASE}" to arm: '
    )

    authorization = ProtocolAuthorization.issue(
        experiment.experiment_id,
        phrase,
    )

    archive = ProtocolArchive()

    with open_controller(
        "cgram-slot0-address-40",
        "/dev/ttyS1",
        1200,
        1.0,
        "development/logs",
    ) as (controller, capture):
        controller.backlight(True)
        controller.clear()

        def observer(item):
            controller.write_frame(
                "CGRAM SLOT 0",
                bytes([0x00] * 16),
            )

            print()
            print(
                "Inspect the second LCD row. "
                "Does it show the checkerboard?"
            )

            answer = input(
                "Enter confirmed, rejected, or inconclusive: "
            ).strip().lower()

            outcomes = {
                "confirmed": ObservationOutcome.CONFIRMED,
                "rejected": ObservationOutcome.REJECTED,
                "inconclusive": ObservationOutcome.INCONCLUSIVE,
            }

            outcome = outcomes.get(
                answer,
                ObservationOutcome.INCONCLUSIVE,
            )

            notes = input(
                "Describe what appeared: "
            ).strip()

            return ProtocolObservation(
                experiment_id=item.experiment_id,
                outcome=outcome,
                visible_effect=notes,
                restored=False,
                metadata={
                    "candidate_address": "0x40",
                    "target_slot": 0,
                    "packet_hex": CGRAM_PACKET.hex(" ").upper(),
                },
            )

        runner = ProtocolLiveRunner(
            controller,
            archive=archive,
        )

        run = runner.run(
            experiment,
            authorization,
            observer=observer,
        )

    print()
    print("Run state :", run.state.value)
    print("Capture   :", capture)
    print("Restored  :", run.observations[0].restored)
    print("Outcome   :", run.observations[0].outcome.value)
    print("Archive   : development/protocol")

    if run.error:
        print("Error     :", run.error)

    return 0 if run.state.value == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
