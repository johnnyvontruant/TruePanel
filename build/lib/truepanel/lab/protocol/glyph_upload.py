"""
Custom-glyph upload planning and candidate packet serialization.

The true A125 CGRAM opcode is not yet known. Candidate serializers remain
offline-only until wrapped in an explicitly allowlisted live experiment.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .glyphs import CustomGlyph


A125_HOST_PREAMBLE = 0x4D
CUSTOM_SLOT_COUNT = 8


class GlyphPayloadLayout(str, Enum):
    OPCODE_SLOT_ROWS = "opcode_slot_rows"
    OPCODE_LENGTH_SLOT_ROWS = "opcode_length_slot_rows"
    OPCODE_SLOT_LENGTH_ROWS = "opcode_slot_length_rows"


def validate_slot(slot) -> int:
    if isinstance(slot, bool):
        raise TypeError(
            "glyph slot cannot be boolean"
        )

    try:
        slot = int(slot)
    except (TypeError, ValueError) as error:
        raise TypeError(
            "glyph slot must be an integer"
        ) from error

    if not 0 <= slot < CUSTOM_SLOT_COUNT:
        raise ValueError(
            "glyph slot must be between zero and seven"
        )

    return slot


def validate_opcode(opcode) -> int:
    if isinstance(opcode, bool):
        raise TypeError(
            "opcode cannot be boolean"
        )

    try:
        opcode = int(opcode)
    except (TypeError, ValueError) as error:
        raise TypeError(
            "opcode must be an integer"
        ) from error

    if not 0 <= opcode <= 0xFF:
        raise ValueError(
            "opcode must be between 0x00 and 0xFF"
        )

    return opcode


@dataclass(frozen=True)
class GlyphUploadPlan:
    slot: int
    glyph: CustomGlyph

    def __post_init__(self):
        object.__setattr__(
            self,
            "slot",
            validate_slot(self.slot),
        )

        if not isinstance(
            self.glyph,
            CustomGlyph,
        ):
            raise TypeError(
                "glyph must be a CustomGlyph"
            )

    @property
    def payload(self):
        return self.glyph.payload

    def as_dict(self):
        return {
            "slot": self.slot,
            "slot_hex": f"0x{self.slot:02X}",
            "glyph": self.glyph.as_dict(),
        }


@dataclass(frozen=True)
class CandidateGlyphSerializer:
    opcode: int
    layout: GlyphPayloadLayout

    def __post_init__(self):
        object.__setattr__(
            self,
            "opcode",
            validate_opcode(self.opcode),
        )

        if not isinstance(
            self.layout,
            GlyphPayloadLayout,
        ):
            raise TypeError(
                "layout must be a GlyphPayloadLayout"
            )

    def serialize(
        self,
        plan: GlyphUploadPlan,
    ) -> bytes:
        if not isinstance(
            plan,
            GlyphUploadPlan,
        ):
            raise TypeError(
                "plan must be a GlyphUploadPlan"
            )

        rows = plan.payload
        slot = plan.slot
        length = len(rows)

        if self.layout is GlyphPayloadLayout.OPCODE_SLOT_ROWS:
            body = bytes(
                [self.opcode, slot]
            ) + rows

        elif (
            self.layout
            is GlyphPayloadLayout.OPCODE_LENGTH_SLOT_ROWS
        ):
            body = bytes(
                [self.opcode, length + 1, slot]
            ) + rows

        elif (
            self.layout
            is GlyphPayloadLayout.OPCODE_SLOT_LENGTH_ROWS
        ):
            body = bytes(
                [self.opcode, slot, length]
            ) + rows

        else:
            raise ValueError(
                "unsupported glyph payload layout"
            )

        return bytes(
            [A125_HOST_PREAMBLE]
        ) + body

    def as_dict(self):
        return {
            "opcode": self.opcode,
            "opcode_hex": f"0x{self.opcode:02X}",
            "layout": self.layout.value,
        }
