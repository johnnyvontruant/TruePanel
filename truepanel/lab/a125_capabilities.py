"""Hardware-backed A125 capability providers.

These providers use documented controller operations only. They do not open
the serial port themselves, allowing the laboratory command layer to retain
ownership, capture logging, and safety interlocks.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from truepanel.lab.capabilities import (
    CapabilityProbe,
    CapabilityProbeResult,
    ProbeOutcome,
    ProbeSafety,
    StaticCapabilityProvider,
)


@dataclass(frozen=True)
class A125IdentitySample:
    """One normalized documented A125 identity-query result."""

    capability: str
    opcode: int
    value: int
    latency_ms: float

    @property
    def value_hex(self) -> str:
        return f"0x{self.value:04X}"


def _run_identity_query(
    *,
    capability: str,
    opcode: int,
    query: Callable[[], int],
) -> CapabilityProbeResult:
    """Execute one documented A125 identity query."""

    started = time.perf_counter()
    value = int(query())
    latency_ms = (time.perf_counter() - started) * 1000.0

    if not 0 <= value <= 0xFFFF:
        raise ValueError(
            f"{capability} returned a value outside 16 bits: {value}"
        )

    sample = A125IdentitySample(
        capability=capability,
        opcode=opcode,
        value=value,
        latency_ms=latency_ms,
    )

    return CapabilityProbeResult(
        capability=capability,
        outcome=ProbeOutcome.SUPPORTED,
        detail=(
            f"Documented opcode 0x{opcode:02X} returned "
            f"{sample.value_hex} in {latency_ms:.3f} ms"
        ),
        successful_samples=1,
        total_samples=1,
        metadata={
            "opcode": opcode,
            "opcode_hex": f"0x{opcode:02X}",
            "value": value,
            "value_hex": sample.value_hex,
            "latency_ms": latency_ms,
            "safety": ProbeSafety.DOCUMENTED_READ_ONLY.value,
        },
    )


class A125IdentityCapabilityProvider(StaticCapabilityProvider):
    """Detect documented A125 identity and input capabilities."""

    def __init__(self, controller) -> None:
        self.controller = controller

        super().__init__(
            name="a125_identity",
            category="controller",
            items=[
                CapabilityProbe(
                    name="a125_board_query",
                    capability="board_query",
                    safety=ProbeSafety.DOCUMENTED_READ_ONLY,
                    description=(
                        "Verify the documented A125 board-ID query."
                    ),
                    execute=lambda: _run_identity_query(
                        capability="board_query",
                        opcode=0x00,
                        query=self.controller.query_board_id,
                    ),
                ),
                CapabilityProbe(
                    name="a125_version_query",
                    capability="version_query",
                    safety=ProbeSafety.DOCUMENTED_READ_ONLY,
                    description=(
                        "Verify the documented A125 protocol-version query."
                    ),
                    execute=lambda: _run_identity_query(
                        capability="version_query",
                        opcode=0x07,
                        query=self.controller.query_protocol_version,
                    ),
                ),
                CapabilityProbe(
                    name="a125_button_query",
                    capability="button_query",
                    safety=ProbeSafety.DOCUMENTED_READ_ONLY,
                    description=(
                        "Verify the documented A125 button-status query."
                    ),
                    execute=lambda: _run_identity_query(
                        capability="button_query",
                        opcode=0x06,
                        query=self.controller.query_buttons,
                    ),
                ),
            ],
        )


def build_a125_read_only_providers(
    controller,
) -> tuple[StaticCapabilityProvider, ...]:
    """Build all currently approved read-only A125 providers."""

    return (
        A125IdentityCapabilityProvider(controller),
    )
