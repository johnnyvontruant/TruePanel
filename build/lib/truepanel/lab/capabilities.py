"""Capability detection for the Project Stargate laboratory.

Capability probes describe a controller feature and produce normalized
outcomes. The detector converts those outcomes into fingerprint observations
without performing serial I/O itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Callable,
    Iterable,
    Mapping,
    Protocol,
    runtime_checkable,
)

from truepanel.lab.fingerprint import (
    CapabilityState,
    FingerprintEvidence,
)
from truepanel.lab.fingerprint_builder import CapabilityObservation


class ProbeSafety(str, Enum):
    """Safety classification for a capability probe."""

    PASSIVE = "passive"
    DOCUMENTED_READ_ONLY = "documented_read_only"
    DOCUMENTED_STATEFUL = "documented_stateful"
    EXPERIMENTAL_READ_ONLY = "experimental_read_only"
    EXPERIMENTAL_STATEFUL = "experimental_stateful"


class ProbeOutcome(str, Enum):
    """Normalized result returned by a capability probe."""

    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    EXPERIMENTAL = "experimental"
    INCONCLUSIVE = "inconclusive"
    ERROR = "error"


@dataclass(frozen=True)
class CapabilityProbeResult:
    """Result from one capability probe execution."""

    capability: str
    outcome: ProbeOutcome
    detail: str
    successful_samples: int = 1
    total_samples: int = 1
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized = self.capability.strip().lower().replace(" ", "_")

        if not normalized:
            raise ValueError("capability must not be empty")

        object.__setattr__(self, "capability", normalized)

        if not self.detail.strip():
            raise ValueError("probe result detail must not be empty")

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
        return self.successful_samples / self.total_samples


@dataclass(frozen=True)
class CapabilityProbe:
    """Definition of one capability detection operation."""

    name: str
    capability: str
    safety: ProbeSafety
    execute: Callable[[], CapabilityProbeResult]
    description: str = ""

    def __post_init__(self) -> None:
        name = self.name.strip().lower().replace(" ", "_")
        capability = self.capability.strip().lower().replace(" ", "_")

        if not name:
            raise ValueError("probe name must not be empty")

        if not capability:
            raise ValueError("probe capability must not be empty")

        object.__setattr__(self, "name", name)
        object.__setattr__(self, "capability", capability)


@dataclass
class CapabilityDetectionReport:
    """Aggregate result from a capability detection run."""

    results: list[CapabilityProbeResult] = field(default_factory=list)

    @property
    def supported(self) -> int:
        return sum(
            result.outcome is ProbeOutcome.SUPPORTED
            for result in self.results
        )

    @property
    def unsupported(self) -> int:
        return sum(
            result.outcome is ProbeOutcome.UNSUPPORTED
            for result in self.results
        )

    @property
    def experimental(self) -> int:
        return sum(
            result.outcome is ProbeOutcome.EXPERIMENTAL
            for result in self.results
        )

    @property
    def inconclusive(self) -> int:
        return sum(
            result.outcome
            in {
                ProbeOutcome.INCONCLUSIVE,
                ProbeOutcome.ERROR,
            }
            for result in self.results
        )

    @property
    def healthy(self) -> bool:
        return bool(self.results) and all(
            result.outcome is not ProbeOutcome.ERROR
            for result in self.results
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "healthy": self.healthy,
            "total": len(self.results),
            "supported": self.supported,
            "unsupported": self.unsupported,
            "experimental": self.experimental,
            "inconclusive": self.inconclusive,
            "results": [
                {
                    "capability": result.capability,
                    "outcome": result.outcome.value,
                    "detail": result.detail,
                    "successful_samples": result.successful_samples,
                    "total_samples": result.total_samples,
                    "confidence": round(result.confidence, 6),
                    "metadata": dict(result.metadata),
                }
                for result in self.results
            ],
        }


_OUTCOME_TO_STATE = {
    ProbeOutcome.SUPPORTED: CapabilityState.SUPPORTED,
    ProbeOutcome.UNSUPPORTED: CapabilityState.UNSUPPORTED,
    ProbeOutcome.EXPERIMENTAL: CapabilityState.EXPERIMENTAL,
    ProbeOutcome.INCONCLUSIVE: CapabilityState.UNKNOWN,
    ProbeOutcome.ERROR: CapabilityState.UNKNOWN,
}


class CapabilityRegistry:
    """Registry of unique capability probes."""

    def __init__(
        self,
        probes: Iterable[CapabilityProbe] = (),
    ) -> None:
        self._probes: dict[str, CapabilityProbe] = {}

        for probe in probes:
            self.register(probe)

    def register(self, probe: CapabilityProbe) -> None:
        if probe.name in self._probes:
            raise ValueError(
                f"capability probe already registered: {probe.name}"
            )

        self._probes[probe.name] = probe

    def get(self, name: str) -> CapabilityProbe:
        normalized = name.strip().lower().replace(" ", "_")

        try:
            return self._probes[normalized]
        except KeyError as error:
            raise KeyError(
                f"unknown capability probe: {normalized}"
            ) from error

    def all(self) -> tuple[CapabilityProbe, ...]:
        return tuple(
            self._probes[name]
            for name in sorted(self._probes)
        )


class CapabilityDetector:
    """Execute approved probes and normalize their results."""

    def __init__(
        self,
        registry: CapabilityRegistry,
    ) -> None:
        self._registry = registry

    def detect(
        self,
        *,
        probe_names: Iterable[str] | None = None,
        allowed_safety: Iterable[ProbeSafety] = (
            ProbeSafety.PASSIVE,
            ProbeSafety.DOCUMENTED_READ_ONLY,
        ),
    ) -> CapabilityDetectionReport:
        allowed = set(allowed_safety)

        probes = (
            self._registry.all()
            if probe_names is None
            else tuple(
                self._registry.get(name)
                for name in probe_names
            )
        )

        report = CapabilityDetectionReport()

        for probe in probes:
            if probe.safety not in allowed:
                raise PermissionError(
                    f"capability probe {probe.name!r} requires "
                    f"safety authorization {probe.safety.value!r}"
                )

            try:
                result = probe.execute()
            except Exception as error:
                result = CapabilityProbeResult(
                    capability=probe.capability,
                    outcome=ProbeOutcome.ERROR,
                    detail=str(error),
                    successful_samples=0,
                    total_samples=1,
                    metadata={
                        "probe": probe.name,
                        "safety": probe.safety.value,
                    },
                )

            if result.capability != probe.capability:
                raise ValueError(
                    f"probe {probe.name!r} returned capability "
                    f"{result.capability!r}; expected "
                    f"{probe.capability!r}"
                )

            report.results.append(result)

        return report


def result_to_observation(
    result: CapabilityProbeResult,
    *,
    source: str = "capability-detector",
) -> CapabilityObservation:
    """Convert one probe result into a fingerprint observation."""

    evidence = FingerprintEvidence(
        source=source,
        observation=result.detail,
        successful_samples=result.successful_samples,
        total_samples=result.total_samples,
    )

    return CapabilityObservation(
        name=result.capability,
        state=_OUTCOME_TO_STATE[result.outcome],
        evidence=(evidence,),
        notes=result.detail,
    )


def report_to_observations(
    report: CapabilityDetectionReport,
    *,
    source: str = "capability-detector",
) -> tuple[CapabilityObservation, ...]:
    """Convert all detection results into fingerprint observations."""

    return tuple(
        result_to_observation(result, source=source)
        for result in report.results
    )


@runtime_checkable
class CapabilityProvider(Protocol):
    """Provider that detects a related family of capabilities."""

    name: str
    category: str

    def detect(
        self,
        *,
        allowed_safety: Iterable[ProbeSafety],
    ) -> CapabilityDetectionReport:
        """Run this provider's capability detection procedure."""


@dataclass
class StaticCapabilityProvider:
    """Simple provider for built-ins, adapters, plugins, and tests."""

    name: str
    category: str
    items: list[CapabilityProbe] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.name = self.name.strip().lower().replace(" ", "_")
        self.category = self.category.strip().lower().replace(" ", "_")

        if not self.name:
            raise ValueError("capability provider name must not be empty")

        if not self.category:
            raise ValueError(
                "capability provider category must not be empty"
            )

    def probes(self) -> Iterable[CapabilityProbe]:
        """Return the simple probes owned by this provider."""

        return tuple(self.items)

    def detect(
        self,
        *,
        allowed_safety: Iterable[ProbeSafety],
    ) -> CapabilityDetectionReport:
        """Detect capabilities using this provider's probe collection."""

        registry = CapabilityRegistry(self.probes())
        detector = CapabilityDetector(registry)

        return detector.detect(
            allowed_safety=allowed_safety,
        )


@dataclass
class CapabilityProviderResult:
    """Detection result attributed to one capability provider."""

    provider: str
    category: str
    report: CapabilityDetectionReport

    @property
    def healthy(self) -> bool:
        return self.report.healthy

    def as_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "category": self.category,
            "healthy": self.healthy,
            "report": self.report.as_dict(),
        }


@dataclass
class CapabilityProviderReport:
    """Aggregate result from multiple capability providers."""

    providers: list[CapabilityProviderResult] = field(
        default_factory=list
    )

    @property
    def results(self) -> list[CapabilityProbeResult]:
        return [
            result
            for provider in self.providers
            for result in provider.report.results
        ]

    @property
    def healthy(self) -> bool:
        return bool(self.providers) and all(
            provider.healthy for provider in self.providers
        )

    @property
    def supported(self) -> int:
        return sum(
            provider.report.supported
            for provider in self.providers
        )

    @property
    def unsupported(self) -> int:
        return sum(
            provider.report.unsupported
            for provider in self.providers
        )

    @property
    def experimental(self) -> int:
        return sum(
            provider.report.experimental
            for provider in self.providers
        )

    @property
    def inconclusive(self) -> int:
        return sum(
            provider.report.inconclusive
            for provider in self.providers
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "healthy": self.healthy,
            "provider_count": len(self.providers),
            "result_count": len(self.results),
            "supported": self.supported,
            "unsupported": self.unsupported,
            "experimental": self.experimental,
            "inconclusive": self.inconclusive,
            "providers": [
                provider.as_dict()
                for provider in self.providers
            ],
        }


class CapabilityProviderRegistry:
    """Registry of unique capability providers."""

    def __init__(
        self,
        providers: Iterable[CapabilityProvider] = (),
    ) -> None:
        self._providers: dict[str, CapabilityProvider] = {}

        for provider in providers:
            self.register(provider)

    def register(self, provider: CapabilityProvider) -> None:
        if not isinstance(provider, CapabilityProvider):
            raise TypeError(
                "capability provider must expose name, category, "
                "and detect()"
            )

        name = provider.name.strip().lower().replace(" ", "_")

        if not name:
            raise ValueError(
                "capability provider name must not be empty"
            )

        if name in self._providers:
            raise ValueError(
                f"capability provider already registered: {name}"
            )

        self._providers[name] = provider

    def get(self, name: str) -> CapabilityProvider:
        normalized = name.strip().lower().replace(" ", "_")

        try:
            return self._providers[normalized]
        except KeyError as error:
            raise KeyError(
                f"unknown capability provider: {normalized}"
            ) from error

    def all(self) -> tuple[CapabilityProvider, ...]:
        return tuple(
            self._providers[name]
            for name in sorted(self._providers)
        )


class CapabilityProviderDetector:
    """Run capability detection provider by provider."""

    def __init__(
        self,
        registry: CapabilityProviderRegistry,
    ) -> None:
        self._registry = registry

    def detect(
        self,
        *,
        provider_names: Iterable[str] | None = None,
        allowed_safety: Iterable[ProbeSafety] = (
            ProbeSafety.PASSIVE,
            ProbeSafety.DOCUMENTED_READ_ONLY,
        ),
    ) -> CapabilityProviderReport:
        providers = (
            self._registry.all()
            if provider_names is None
            else tuple(
                self._registry.get(name)
                for name in provider_names
            )
        )

        report = CapabilityProviderReport()

        for provider in providers:
            provider_name = (
                provider.name.strip().lower().replace(" ", "_")
            )
            category = (
                provider.category.strip().lower().replace(" ", "_")
            )

            if not provider_name:
                raise ValueError(
                    "capability provider name must not be empty"
                )

            if not category:
                raise ValueError(
                    f"capability provider {provider_name!r} has "
                    "an empty category"
                )

            provider_report = provider.detect(
                allowed_safety=allowed_safety,
            )

            if not isinstance(
                provider_report,
                CapabilityDetectionReport,
            ):
                raise TypeError(
                    f"capability provider {provider_name!r} "
                    "must return CapabilityDetectionReport"
                )

            report.providers.append(
                CapabilityProviderResult(
                    provider=provider_name,
                    category=category,
                    report=provider_report,
                )
            )

        return report


def provider_report_to_observations(
    report: CapabilityProviderReport,
) -> tuple[CapabilityObservation, ...]:
    """Convert provider results into fingerprint observations."""

    observations: list[CapabilityObservation] = []

    for provider in report.providers:
        source = f"capability-provider:{provider.provider}"

        observations.extend(
            report_to_observations(
                provider.report,
                source=source,
            )
        )

    return tuple(observations)
