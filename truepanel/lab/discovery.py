"""
Project Stargate Discovery Engine.

The Discovery Engine orchestrates safe hardware probes and combines identity,
timing, response classification, and survey observations into one report.

This initial implementation executes documented read-only A125 queries only.
It does not transmit undocumented commands or commands that change state.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from truepanel.diagnostics.protocol import (
    A125Reply,
    A125Response,
)
from truepanel.lab.classifier import (
    ClassifiedResponse,
    ResponseClassification,
    classify_error,
    classify_reply,
)
from truepanel.lab.statistics import (
    LatencySummary,
    summarize_latencies,
)
from truepanel.lab.survey import (
    SAFE_READ_ONLY_OPCODES,
    SurveyObservation,
    classify_opcode,
    validate_survey_opcodes,
)


@dataclass(frozen=True)
class DiscoveryProbe:
    """
    One documented read-only discovery operation.

    The query callable returns the numeric value decoded by A125Controller.
    """

    name: str
    opcode: int
    expected_response: int
    query: Callable[[], int]


@dataclass(frozen=True)
class DiscoveryProbeResult:
    name: str
    opcode: int
    success: bool
    latency_ms: float
    value: int | None
    response: ClassifiedResponse

    @property
    def value_hex(self) -> str:
        if self.value is None:
            return ""

        return f"0x{self.value:04X}"

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "opcode": self.opcode,
            "opcode_hex": f"0x{self.opcode:02X}",
            "success": self.success,
            "latency_ms": self.latency_ms,
            "value": self.value,
            "value_hex": self.value_hex or None,
            "response": self.response.as_dict(),
        }


@dataclass
class DiscoveryReport:
    started_at: str
    completed_at: str = ""
    board_id: int | None = None
    protocol_version: int | None = None
    button_status: int | None = None
    results: list[DiscoveryProbeResult] = field(default_factory=list)
    observations: list[SurveyObservation] = field(default_factory=list)

    @property
    def successes(self) -> int:
        return sum(1 for result in self.results if result.success)

    @property
    def failures(self) -> int:
        return sum(1 for result in self.results if not result.success)

    @property
    def healthy(self) -> bool:
        return bool(self.results) and self.failures == 0

    @property
    def latency(self) -> LatencySummary:
        return summarize_latencies(
            [
                result.latency_ms
                for result in self.results
                if result.success
            ]
        )

    def add(self, result: DiscoveryProbeResult) -> None:
        self.results.append(result)
        self.observations.append(
            SurveyObservation(
                opcode=result.opcode,
                response=result.response,
                latency_ms=result.latency_ms,
            )
        )

        if not result.success:
            return

        if result.name == "board":
            self.board_id = result.value
        elif result.name == "version":
            self.protocol_version = result.value
        elif result.name == "buttons":
            self.button_status = result.value

    def as_dict(self) -> dict[str, object]:
        return {
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "healthy": self.healthy,
            "successes": self.successes,
            "failures": self.failures,
            "board_id": self.board_id,
            "board_id_hex": (
                f"0x{self.board_id:04X}"
                if self.board_id is not None
                else None
            ),
            "protocol_version": self.protocol_version,
            "protocol_version_hex": (
                f"0x{self.protocol_version:04X}"
                if self.protocol_version is not None
                else None
            ),
            "button_status": self.button_status,
            "button_status_hex": (
                f"0x{self.button_status:04X}"
                if self.button_status is not None
                else None
            ),
            "latency": self.latency.as_dict(),
            "results": [
                result.as_dict()
                for result in self.results
            ],
            "observations": [
                observation.as_dict()
                for observation in self.observations
            ],
        }


def build_a125_probes(controller) -> list[DiscoveryProbe]:
    """Build the default documented read-only A125 discovery plan."""

    return [
        DiscoveryProbe(
            name="board",
            opcode=0x00,
            expected_response=A125Response.BOARD_ID,
            query=controller.query_board_id,
        ),
        DiscoveryProbe(
            name="version",
            opcode=0x07,
            expected_response=A125Response.PROTOCOL_VERSION,
            query=controller.query_protocol_version,
        ),
        DiscoveryProbe(
            name="buttons",
            opcode=0x06,
            expected_response=A125Response.BUTTON_STATUS,
            query=controller.query_buttons,
        ),
    ]


def validate_discovery_plan(
    probes: list[DiscoveryProbe],
) -> None:
    """
    Verify that a discovery plan contains safe read-only opcodes only.

    The Discovery Engine deliberately has no override for this restriction.
    Experimental exploration belongs to a separate explicitly armed runner.
    """

    opcodes = [probe.opcode for probe in probes]

    validate_survey_opcodes(
        opcodes,
        allow_experimental_read_only=False,
        allow_experimental_stateful=False,
        allow_documented_writes=False,
    )

    for probe in probes:
        policy = classify_opcode(probe.opcode)

        if probe.opcode not in SAFE_READ_ONLY_OPCODES:
            raise PermissionError(
                f"Discovery probe {probe.name!r} uses non-read-only "
                f"opcode 0x{probe.opcode:02X}"
            )

        if not policy.permitted_by_default:
            raise PermissionError(
                f"Discovery probe {probe.name!r} is not permitted "
                "by the default safety policy"
            )


def _reply_for_value(
    expected_response: int,
    value: int,
) -> A125Reply:
    """Create a normalized classified reply from a decoded query value."""

    if not 0 <= value <= 0xFFFF:
        raise ValueError(
            f"Discovery value must fit in 16 bits: {value}"
        )

    return A125Reply(
        preamble=0x53,
        response=int(expected_response),
        payload=value.to_bytes(2, "big"),
    )


def run_probe(probe: DiscoveryProbe) -> DiscoveryProbeResult:
    """Execute and classify one discovery probe."""

    started = time.perf_counter()

    try:
        value = int(probe.query())
        elapsed_ms = (
            time.perf_counter() - started
        ) * 1000.0

        response = classify_reply(
            _reply_for_value(
                probe.expected_response,
                value,
            )
        )

        success = (
            response.classification
            == ResponseClassification.KNOWN_RESPONSE
        )

        return DiscoveryProbeResult(
            name=probe.name,
            opcode=probe.opcode,
            success=success,
            latency_ms=elapsed_ms,
            value=value,
            response=response,
        )
    except Exception as error:
        elapsed_ms = (
            time.perf_counter() - started
        ) * 1000.0

        return DiscoveryProbeResult(
            name=probe.name,
            opcode=probe.opcode,
            success=False,
            latency_ms=elapsed_ms,
            value=None,
            response=classify_error(error),
        )


def run_discovery(
    controller,
    probe_callback: (
        Callable[[DiscoveryProbeResult], None] | None
    ) = None,
) -> DiscoveryReport:
    """Run the complete safe A125 discovery plan."""

    probes = build_a125_probes(controller)
    validate_discovery_plan(probes)

    report = DiscoveryReport(
        started_at=datetime.now().isoformat(
            timespec="seconds"
        )
    )

    for probe in probes:
        result = run_probe(probe)
        report.add(result)

        if probe_callback is not None:
            probe_callback(result)

    report.completed_at = datetime.now().isoformat(
        timespec="seconds"
    )

    return report
