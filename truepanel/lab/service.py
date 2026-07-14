"""Public service layer for the Project Stargate laboratory.

The service shields callers from fingerprint assembly details. CLI commands,
plugins, reports, and future dashboards should use LaboratoryService instead
of constructing FingerprintBuilder instances directly.
"""

from __future__ import annotations

from collections.abc import Iterable

from truepanel.lab.a125_capabilities import (
    build_a125_read_only_providers,
)
from truepanel.lab.capabilities import (
    CapabilityDetectionReport,
    CapabilityProbeResult,
    CapabilityProviderDetector,
    CapabilityProviderRegistry,
    CapabilityProviderReport,
    CapabilityProviderResult,
    ProbeOutcome,
)
from truepanel.lab.fingerprint import ControllerFingerprint
from truepanel.lab.fingerprint_builder import (
    FingerprintBuilder,
    FingerprintProvider,
)


class LaboratoryService:
    """Public application service for laboratory operations."""

    def __init__(
        self,
        *,
        baseline: ControllerFingerprint | None = None,
        providers: Iterable[FingerprintProvider] = (),
    ) -> None:
        self._baseline = baseline
        self._providers = tuple(providers)

    @property
    def providers(self) -> tuple[FingerprintProvider, ...]:
        """Return the configured fingerprint providers."""

        return self._providers

    def build_fingerprint(
        self,
        providers: Iterable[FingerprintProvider] = (),
    ) -> ControllerFingerprint:
        """Build the current canonical controller fingerprint.

        Providers passed to this method are appended after providers configured
        on the service. Later observations therefore retain the builder's
        existing last-observation-wins behavior.
        """

        combined_providers = self._providers + tuple(providers)

        builder = FingerprintBuilder(baseline=self._baseline)
        return builder.build(combined_providers)

    def build_baseline_capability_report(
        self,
    ) -> CapabilityProviderReport:
        """Build a capability report from recorded baseline knowledge."""

        fingerprint = self.build_fingerprint()
        results = []

        state_to_outcome = {
            "supported": ProbeOutcome.SUPPORTED,
            "unsupported": ProbeOutcome.UNSUPPORTED,
            "experimental": ProbeOutcome.EXPERIMENTAL,
            "unknown": ProbeOutcome.INCONCLUSIVE,
        }

        for capability in fingerprint.capabilities.values():
            evidence_successes = sum(
                item.successful_samples
                for item in capability.evidence
            )
            evidence_total = sum(
                item.total_samples
                for item in capability.evidence
            )

            results.append(
                CapabilityProbeResult(
                    capability=capability.name,
                    outcome=state_to_outcome[
                        capability.state.value
                    ],
                    detail=(
                        capability.notes
                        or "Recorded baseline capability knowledge."
                    ),
                    successful_samples=evidence_successes,
                    total_samples=max(1, evidence_total),
                    metadata={
                        "source": "baseline-fingerprint",
                        "live": False,
                    },
                )
            )

        detection_report = CapabilityDetectionReport(
            results=results
        )

        return CapabilityProviderReport(
            providers=[
                CapabilityProviderResult(
                    provider="a125_baseline",
                    category="controller",
                    report=detection_report,
                )
            ]
        )

    def detect_capabilities(
        self,
        controller,
    ) -> CapabilityProviderReport:
        """Run all currently approved read-only capability providers."""

        providers = build_a125_read_only_providers(controller)
        registry = CapabilityProviderRegistry(providers)

        return CapabilityProviderDetector(registry).detect()

    def with_providers(
        self,
        providers: Iterable[FingerprintProvider],
    ) -> "LaboratoryService":
        """Return a new service containing additional providers."""

        return LaboratoryService(
            baseline=self._baseline,
            providers=self._providers + tuple(providers),
        )
