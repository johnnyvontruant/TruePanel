"""Public service layer for the Project Stargate laboratory.

The service shields callers from fingerprint assembly details. CLI commands,
plugins, reports, and future dashboards should use LaboratoryService instead
of constructing FingerprintBuilder instances directly.
"""

from __future__ import annotations

from collections.abc import Iterable

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

    def with_providers(
        self,
        providers: Iterable[FingerprintProvider],
    ) -> "LaboratoryService":
        """Return a new service containing additional providers."""

        return LaboratoryService(
            baseline=self._baseline,
            providers=self._providers + tuple(providers),
        )
