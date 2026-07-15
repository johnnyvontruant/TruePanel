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
    provider_report_to_observations,
)
from truepanel.lab.fingerprint import ControllerFingerprint
from truepanel.lab.fingerprint_builder import (
    FingerprintBuilder,
    FingerprintProvider,
    IdentityObservation,
    MetadataObservation,
    StaticFingerprintProvider,
    TimingObservation,
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

    def build_live_fingerprint(
        self,
        controller,
        *,
        capture_path: str = "",
    ) -> tuple[
        ControllerFingerprint,
        CapabilityProviderReport,
    ]:
        """Build a live fingerprint from capability-provider evidence."""

        capability_report = self.detect_capabilities(controller)

        results = {
            result.capability: result
            for result in capability_report.results
        }

        board_result = results.get("board_query")
        version_result = results.get("version_query")

        observations = list(
            provider_report_to_observations(capability_report)
        )

        observations.append(
            IdentityObservation(
                board_id=(
                    str(board_result.metadata.get("value_hex"))
                    if board_result is not None
                    and board_result.metadata.get("value_hex")
                    else None
                ),
                firmware_version=(
                    str(version_result.metadata.get("value_hex"))
                    if version_result is not None
                    and version_result.metadata.get("value_hex")
                    else None
                ),
            )
        )

        latencies = [
            float(result.metadata["latency_ms"])
            for result in capability_report.results
            if "latency_ms" in result.metadata
        ]

        if latencies:
            observations.append(
                TimingObservation(
                    average_latency_ms=(
                        sum(latencies) / len(latencies)
                    ),
                    successful_samples=capability_report.supported,
                    total_samples=len(capability_report.results),
                    source="capability-provider-pipeline",
                )
            )

        observations.append(
            MetadataObservation(
                values={
                    "acquisition_mode": "live",
                    "capture_path": capture_path,
                    "capability_provider_count": len(
                        capability_report.providers
                    ),
                    "capability_result_count": len(
                        capability_report.results
                    ),
                    "capability_supported": (
                        capability_report.supported
                    ),
                    "capability_unsupported": (
                        capability_report.unsupported
                    ),
                    "capability_experimental": (
                        capability_report.experimental
                    ),
                    "capability_inconclusive": (
                        capability_report.inconclusive
                    ),
                    "capability_healthy": (
                        capability_report.healthy
                    ),
                }
            )
        )

        fingerprint_provider = StaticFingerprintProvider(
            name="live-capability-pipeline",
            items=observations,
        )

        fingerprint = self.build_fingerprint(
            [fingerprint_provider]
        )

        return fingerprint, capability_report

    def with_providers(
        self,
        providers: Iterable[FingerprintProvider],
    ) -> "LaboratoryService":
        """Return a new service containing additional providers."""

        return LaboratoryService(
            baseline=self._baseline,
            providers=self._providers + tuple(providers),
        )
