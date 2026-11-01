"""
Build offline CGRAM upload experiments.
"""

from __future__ import annotations

from .experiment import (
    ExperimentRisk,
    ProtocolExperiment,
    ProtocolHypothesis,
)
from .glyph_upload import (
    CandidateGlyphSerializer,
    GlyphUploadPlan,
)
from .sequence import (
    ProtocolSequence,
    ProtocolStep,
    StepOperation,
)


DISPLAY_CLEAR_PACKET = b"\x4D\x0D"


def build_glyph_upload_experiment(
    plan: GlyphUploadPlan,
    serializer: CandidateGlyphSerializer,
    *,
    repeat_count=1,
    restore_packet=DISPLAY_CLEAR_PACKET,
):
    packet = serializer.serialize(
        plan
    )

    return ProtocolExperiment(
        name=(
            f"glyph-upload-"
            f"{serializer.opcode:02x}-"
            f"slot-{plan.slot}-"
            f"{serializer.layout.value}"
        ),
        hypothesis=ProtocolHypothesis(
            title=(
                "Candidate custom-glyph upload"
            ),
            statement=(
                f"Opcode 0x{serializer.opcode:02X} "
                f"using layout {serializer.layout.value} "
                f"may program custom slot {plan.slot}."
            ),
            expected_observation=(
                f"Displaying character byte 0x{plan.slot:02X} "
                f"shows glyph {plan.glyph.name}."
            ),
            rejection_condition=(
                "The target slot remains unchanged, "
                "the packet is rejected, or the display becomes unstable."
            ),
        ),
        sequence=ProtocolSequence.from_steps(
            (
                ProtocolStep(
                    operation=StepOperation.TRANSMIT,
                    payload=packet,
                    description=(
                        "Transmit candidate custom-glyph packet"
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
                    operation=StepOperation.DISPLAY_VERIFY,
                    description=(
                        f"Display and inspect custom slot {plan.slot}"
                    ),
                ),
                ProtocolStep(
                    operation=StepOperation.RESTORE,
                    payload=bytes(
                        restore_packet
                    ),
                    description="Restore display",
                ),
            )
        ),
        risk=ExperimentRisk.EXPERIMENTAL_WRITE,
        repeat_count=repeat_count,
        requires_restoration=True,
    )
