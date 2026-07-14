"""Structured controller fingerprints for the Project Stargate laboratory.

A fingerprint records what TruePanel currently knows about a controller
without requiring the controller to be connected when the data is inspected,
serialized, compared, or reported.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping


class CapabilityState(str, Enum):
    """Confidence-neutral state of a detected controller capability."""

    UNKNOWN = "unknown"
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    EXPERIMENTAL = "experimental"


@dataclass(frozen=True)
class FingerprintEvidence:
    """One observation supporting a fingerprint field or capability."""

    source: str
    observation: str
    successful_samples: int = 1
    total_samples: int = 1

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("evidence source must not be empty")

        if not self.observation.strip():
            raise ValueError("evidence observation must not be empty")

        if self.successful_samples < 0:
            raise ValueError("successful_samples must be non-negative")

        if self.total_samples < 1:
            raise ValueError("total_samples must be at least 1")

        if self.successful_samples > self.total_samples:
            raise ValueError(
                "successful_samples cannot exceed total_samples"
            )

    @property
    def confidence(self) -> float:
        """Return this observation's success ratio from 0.0 through 1.0."""

        return self.successful_samples / self.total_samples

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "observation": self.observation,
            "successful_samples": self.successful_samples,
            "total_samples": self.total_samples,
            "confidence": round(self.confidence, 6),
        }


@dataclass
class CapabilityFingerprint:
    """Detected state and evidence for one controller capability."""

    name: str
    state: CapabilityState = CapabilityState.UNKNOWN
    evidence: list[FingerprintEvidence] = field(default_factory=list)
    notes: str | None = None

    def __post_init__(self) -> None:
        normalized = self.name.strip().lower().replace(" ", "_")

        if not normalized:
            raise ValueError("capability name must not be empty")

        self.name = normalized

        if not isinstance(self.state, CapabilityState):
            self.state = CapabilityState(self.state)

    @property
    def confidence(self) -> float:
        """Return weighted confidence derived from all recorded samples."""

        successful = sum(
            item.successful_samples for item in self.evidence
        )
        total = sum(item.total_samples for item in self.evidence)

        if total == 0:
            return 0.0

        return successful / total

    def add_evidence(self, evidence: FingerprintEvidence) -> None:
        self.evidence.append(evidence)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "confidence": round(self.confidence, 6),
            "notes": self.notes,
            "evidence": [item.to_dict() for item in self.evidence],
        }


@dataclass
class ControllerFingerprint:
    """Structured identity and capability profile for one controller."""

    controller_family: str
    board_id: str | None = None
    firmware_version: str | None = None
    display_columns: int | None = None
    display_rows: int | None = None
    serial_port: str | None = None
    baud_rate: int | None = None
    protocol_preamble: int | None = None
    average_latency_ms: float | None = None
    capabilities: dict[str, CapabilityFingerprint] = field(
        default_factory=dict
    )
    metadata: dict[str, Any] = field(default_factory=dict)
    evidence: list[FingerprintEvidence] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.controller_family = self.controller_family.strip()

        if not self.controller_family:
            raise ValueError("controller_family must not be empty")

        if self.display_columns is not None and self.display_columns < 1:
            raise ValueError("display_columns must be positive")

        if self.display_rows is not None and self.display_rows < 1:
            raise ValueError("display_rows must be positive")

        if self.baud_rate is not None and self.baud_rate < 1:
            raise ValueError("baud_rate must be positive")

        if self.protocol_preamble is not None:
            if not 0 <= self.protocol_preamble <= 0xFF:
                raise ValueError(
                    "protocol_preamble must be a single byte"
                )

        if (
            self.average_latency_ms is not None
            and self.average_latency_ms < 0
        ):
            raise ValueError("average_latency_ms must be non-negative")

        existing = list(self.capabilities.values())
        self.capabilities = {}

        for capability in existing:
            self.set_capability(capability)

    @property
    def geometry(self) -> str | None:
        if self.display_columns is None or self.display_rows is None:
            return None

        return f"{self.display_columns}x{self.display_rows}"

    @property
    def confidence(self) -> float:
        """Return weighted confidence across general and capability evidence."""

        evidence: list[FingerprintEvidence] = list(self.evidence)

        for capability in self.capabilities.values():
            evidence.extend(capability.evidence)

        successful = sum(
            item.successful_samples for item in evidence
        )
        total = sum(item.total_samples for item in evidence)

        if total == 0:
            return 0.0

        return successful / total

    def add_evidence(self, evidence: FingerprintEvidence) -> None:
        self.evidence.append(evidence)

    def set_capability(
        self,
        capability: CapabilityFingerprint,
    ) -> None:
        self.capabilities[capability.name] = capability

    def record_capability(
        self,
        name: str,
        state: CapabilityState,
        evidence: Iterable[FingerprintEvidence] = (),
        notes: str | None = None,
    ) -> CapabilityFingerprint:
        capability = CapabilityFingerprint(
            name=name,
            state=state,
            evidence=list(evidence),
            notes=notes,
        )
        self.set_capability(capability)
        return capability

    def merge_metadata(self, values: Mapping[str, Any]) -> None:
        self.metadata.update(values)

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministic JSON-friendly representation."""

        return {
            "schema_version": 1,
            "controller_family": self.controller_family,
            "board_id": self.board_id,
            "firmware_version": self.firmware_version,
            "display": {
                "columns": self.display_columns,
                "rows": self.display_rows,
                "geometry": self.geometry,
            },
            "transport": {
                "serial_port": self.serial_port,
                "baud_rate": self.baud_rate,
                "protocol_preamble": self.protocol_preamble,
            },
            "timing": {
                "average_latency_ms": self.average_latency_ms,
            },
            "confidence": round(self.confidence, 6),
            "capabilities": {
                name: capability.to_dict()
                for name, capability in sorted(
                    self.capabilities.items()
                )
            },
            "metadata": dict(sorted(self.metadata.items())),
            "evidence": [item.to_dict() for item in self.evidence],
        }


def build_a125_baseline_fingerprint() -> ControllerFingerprint:
    """Build the known-safe baseline for the current A125 laboratory target."""

    fingerprint = ControllerFingerprint(
        controller_family="A125",
        serial_port="/dev/ttyS1",
        baud_rate=1200,
        protocol_preamble=0x4D,
    )

    fingerprint.record_capability(
        name="board_query",
        state=CapabilityState.SUPPORTED,
        notes="Verified through repeatable laboratory captures.",
    )
    fingerprint.record_capability(
        name="version_query",
        state=CapabilityState.SUPPORTED,
        notes="Verified through repeatable laboratory captures.",
    )
    fingerprint.record_capability(
        name="button_query",
        state=CapabilityState.SUPPORTED,
        notes="Verified through repeatable laboratory captures.",
    )

    fingerprint.merge_metadata(
        {
            "project": "Project Stargate",
            "safety_class": "known-safe-baseline",
        }
    )

    return fingerprint
