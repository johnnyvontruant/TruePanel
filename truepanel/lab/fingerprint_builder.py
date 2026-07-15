"""Provider-driven controller fingerprint assembly.

Fingerprint providers contribute isolated observations. The builder merges
those observations into one canonical ControllerFingerprint without performing
serial I/O or knowing how the observations were collected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol, runtime_checkable

from truepanel.lab.fingerprint import (
    CapabilityState,
    ControllerFingerprint,
    FingerprintEvidence,
    build_a125_baseline_fingerprint,
)


@dataclass(frozen=True)
class IdentityObservation:
    """Observed controller identity information."""

    board_id: str | None = None
    firmware_version: str | None = None
    evidence: tuple[FingerprintEvidence, ...] = ()


@dataclass(frozen=True)
class DisplayObservation:
    """Observed display geometry."""

    columns: int | None = None
    rows: int | None = None
    evidence: tuple[FingerprintEvidence, ...] = ()


@dataclass(frozen=True)
class TimingObservation:
    """Observed controller response timing."""

    average_latency_ms: float
    successful_samples: int
    total_samples: int
    source: str = "latency"

    def __post_init__(self) -> None:
        if self.average_latency_ms < 0:
            raise ValueError("average_latency_ms must be non-negative")

        if self.successful_samples < 0:
            raise ValueError("successful_samples must be non-negative")

        if self.total_samples < 1:
            raise ValueError("total_samples must be at least 1")

        if self.successful_samples > self.total_samples:
            raise ValueError(
                "successful_samples cannot exceed total_samples"
            )

    def to_evidence(self) -> FingerprintEvidence:
        return FingerprintEvidence(
            source=self.source,
            observation=(
                f"average response latency "
                f"{self.average_latency_ms:.3f} ms"
            ),
            successful_samples=self.successful_samples,
            total_samples=self.total_samples,
        )


@dataclass(frozen=True)
class CapabilityObservation:
    """Observed state of one controller capability."""

    name: str
    state: CapabilityState
    evidence: tuple[FingerprintEvidence, ...] = ()
    notes: str | None = None


@dataclass(frozen=True)
class MetadataObservation:
    """Additional structured fingerprint metadata."""

    values: dict[str, Any] = field(default_factory=dict)


FingerprintObservation = (
    IdentityObservation
    | DisplayObservation
    | TimingObservation
    | CapabilityObservation
    | MetadataObservation
)


@runtime_checkable
class FingerprintProvider(Protocol):
    """Interface implemented by fingerprint knowledge providers."""

    name: str

    def observations(self) -> Iterable[FingerprintObservation]:
        """Return observations contributed by this provider."""


@dataclass
class StaticFingerprintProvider:
    """Simple provider useful for tests, adapters, and plugins."""

    name: str
    items: list[FingerprintObservation] = field(default_factory=list)

    def observations(self) -> Iterable[FingerprintObservation]:
        return tuple(self.items)


class FingerprintBuilder:
    """Merge provider observations into a controller fingerprint."""

    def __init__(
        self,
        baseline: ControllerFingerprint | None = None,
    ) -> None:
        self._baseline = baseline

    def build(
        self,
        providers: Iterable[FingerprintProvider] = (),
    ) -> ControllerFingerprint:
        fingerprint = self._copy_baseline()

        for provider in providers:
            if not isinstance(provider, FingerprintProvider):
                raise TypeError(
                    "fingerprint provider must expose a name and "
                    "observations()"
                )

            provider_name = provider.name.strip()
            if not provider_name:
                raise ValueError("fingerprint provider name must not be empty")

            for observation in provider.observations():
                self._apply_observation(
                    fingerprint=fingerprint,
                    observation=observation,
                    provider_name=provider_name,
                )

        return fingerprint

    def _copy_baseline(self) -> ControllerFingerprint:
        baseline = self._baseline or build_a125_baseline_fingerprint()

        fingerprint = ControllerFingerprint(
            controller_family=baseline.controller_family,
            board_id=baseline.board_id,
            firmware_version=baseline.firmware_version,
            display_columns=baseline.display_columns,
            display_rows=baseline.display_rows,
            serial_port=baseline.serial_port,
            baud_rate=baseline.baud_rate,
            protocol_preamble=baseline.protocol_preamble,
            average_latency_ms=baseline.average_latency_ms,
            metadata=dict(baseline.metadata),
            evidence=list(baseline.evidence),
        )

        for capability in baseline.capabilities.values():
            fingerprint.record_capability(
                name=capability.name,
                state=capability.state,
                evidence=list(capability.evidence),
                notes=capability.notes,
            )

        return fingerprint

    def _apply_observation(
        self,
        fingerprint: ControllerFingerprint,
        observation: FingerprintObservation,
        provider_name: str,
    ) -> None:
        if isinstance(observation, IdentityObservation):
            self._apply_identity(fingerprint, observation)
            return

        if isinstance(observation, DisplayObservation):
            self._apply_display(fingerprint, observation)
            return

        if isinstance(observation, TimingObservation):
            fingerprint.average_latency_ms = (
                observation.average_latency_ms
            )
            fingerprint.add_evidence(observation.to_evidence())
            return

        if isinstance(observation, CapabilityObservation):
            self._apply_capability(fingerprint, observation)
            return

        if isinstance(observation, MetadataObservation):
            fingerprint.merge_metadata(observation.values)
            return

        raise TypeError(
            f"provider {provider_name!r} returned unsupported "
            f"observation type {type(observation).__name__}"
        )

    @staticmethod
    def _apply_identity(
        fingerprint: ControllerFingerprint,
        observation: IdentityObservation,
    ) -> None:
        if observation.board_id is not None:
            fingerprint.board_id = observation.board_id

        if observation.firmware_version is not None:
            fingerprint.firmware_version = observation.firmware_version

        for evidence in observation.evidence:
            fingerprint.add_evidence(evidence)

    @staticmethod
    def _apply_display(
        fingerprint: ControllerFingerprint,
        observation: DisplayObservation,
    ) -> None:
        if observation.columns is not None:
            if observation.columns < 1:
                raise ValueError("display columns must be positive")
            fingerprint.display_columns = observation.columns

        if observation.rows is not None:
            if observation.rows < 1:
                raise ValueError("display rows must be positive")
            fingerprint.display_rows = observation.rows

        for evidence in observation.evidence:
            fingerprint.add_evidence(evidence)

    @staticmethod
    def _apply_capability(
        fingerprint: ControllerFingerprint,
        observation: CapabilityObservation,
    ) -> None:
        existing = fingerprint.capabilities.get(
            observation.name.strip().lower().replace(" ", "_")
        )

        combined_evidence = list(observation.evidence)

        if existing is not None:
            combined_evidence = (
                list(existing.evidence) + combined_evidence
            )

        fingerprint.record_capability(
            name=observation.name,
            state=observation.state,
            evidence=combined_evidence,
            notes=observation.notes,
        )


def build_live_a125_fingerprint(
    *,
    board_id: str | None = None,
    firmware_version: str | None = None,
    average_latency_ms: float | None = None,
    successful_samples: int = 0,
    total_samples: int = 0,
) -> ControllerFingerprint:
    """Build an A125 fingerprint from common live laboratory results."""

    observations: list[FingerprintObservation] = []

    if board_id is not None or firmware_version is not None:
        identity_evidence: list[FingerprintEvidence] = []

        if board_id is not None:
            identity_evidence.append(
                FingerprintEvidence(
                    source="board-query",
                    observation=f"board identifier {board_id}",
                )
            )

        if firmware_version is not None:
            identity_evidence.append(
                FingerprintEvidence(
                    source="version-query",
                    observation=(
                        f"firmware version {firmware_version}"
                    ),
                )
            )

        observations.append(
            IdentityObservation(
                board_id=board_id,
                firmware_version=firmware_version,
                evidence=tuple(identity_evidence),
            )
        )

    if average_latency_ms is not None:
        if total_samples < 1:
            raise ValueError(
                "total_samples must be provided with latency data"
            )

        observations.append(
            TimingObservation(
                average_latency_ms=average_latency_ms,
                successful_samples=successful_samples,
                total_samples=total_samples,
                source="repeat",
            )
        )

    provider = StaticFingerprintProvider(
        name="a125-live-results",
        items=observations,
    )

    return FingerprintBuilder().build([provider])
