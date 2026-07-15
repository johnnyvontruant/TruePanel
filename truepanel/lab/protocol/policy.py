"""
Safety policy for live protocol-discovery experiments.
"""

from __future__ import annotations

from dataclasses import dataclass, field


A125_PREAMBLE = 0x4D

DISPLAY_WRITE = 0x0C
DISPLAY_CLEAR = 0x0D
BACKLIGHT = 0x5E
RESET = 0xFF

SAFE_DISPLAY_OPCODES = frozenset(
    {
        DISPLAY_WRITE,
        DISPLAY_CLEAR,
        BACKLIGHT,
    }
)

FORBIDDEN_OPCODES = frozenset(
    {
        RESET,
    }
)


@dataclass(frozen=True)
class ProtocolPolicy:
    """
    Live protocol policy.

    experimental_opcodes contains only opcodes explicitly approved for the
    current research session. Nothing unknown is approved by default.
    """

    experimental_opcodes: frozenset[int] = field(
        default_factory=frozenset
    )
    maximum_packet_bytes: int = 32
    maximum_transmit_steps: int = 4
    maximum_total_steps: int = 12
    maximum_repeat_count: int = 3
    maximum_delay_seconds: float = 2.0

    def __post_init__(self):
        normalized = frozenset(
            int(opcode)
            for opcode in self.experimental_opcodes
        )

        for opcode in normalized:
            if not 0 <= opcode <= 0xFF:
                raise ValueError(
                    "experimental opcode must be between 0x00 and 0xFF"
                )

            if opcode in FORBIDDEN_OPCODES:
                raise ValueError(
                    f"forbidden opcode cannot be approved: 0x{opcode:02X}"
                )

        object.__setattr__(
            self,
            "experimental_opcodes",
            normalized,
        )

        if self.maximum_packet_bytes < 2:
            raise ValueError(
                "maximum_packet_bytes must be at least two"
            )

        if self.maximum_transmit_steps < 1:
            raise ValueError(
                "maximum_transmit_steps must be positive"
            )

        if self.maximum_total_steps < 1:
            raise ValueError(
                "maximum_total_steps must be positive"
            )

        if self.maximum_repeat_count < 1:
            raise ValueError(
                "maximum_repeat_count must be positive"
            )

        if self.maximum_delay_seconds <= 0:
            raise ValueError(
                "maximum_delay_seconds must be positive"
            )

    def opcode_allowed(self, opcode: int) -> bool:
        return (
            opcode in SAFE_DISPLAY_OPCODES
            or opcode in self.experimental_opcodes
        )

    def opcode_experimental(self, opcode: int) -> bool:
        return opcode in self.experimental_opcodes

    def as_dict(self):
        return {
            "experimental_opcodes": sorted(
                self.experimental_opcodes
            ),
            "experimental_opcodes_hex": [
                f"0x{opcode:02X}"
                for opcode in sorted(
                    self.experimental_opcodes
                )
            ],
            "maximum_packet_bytes": self.maximum_packet_bytes,
            "maximum_transmit_steps": (
                self.maximum_transmit_steps
            ),
            "maximum_total_steps": (
                self.maximum_total_steps
            ),
            "maximum_repeat_count": (
                self.maximum_repeat_count
            ),
            "maximum_delay_seconds": (
                self.maximum_delay_seconds
            ),
        }
