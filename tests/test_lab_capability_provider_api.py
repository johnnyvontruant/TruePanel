from dataclasses import dataclass

import pytest

from truepanel.lab.capabilities import (
    CapabilityDetectionReport,
    CapabilityProbe,
    CapabilityProbeResult,
    CapabilityProviderDetector,
    CapabilityProviderRegistry,
    ProbeOutcome,
    ProbeSafety,
    StaticCapabilityProvider,
)


def make_result(
    capability: str,
    outcome: ProbeOutcome = ProbeOutcome.SUPPORTED,
) -> CapabilityProbeResult:
    return CapabilityProbeResult(
        capability=capability,
        outcome=outcome,
        detail=f"{capability} detection completed",
    )


def test_static_provider_detects_through_internal_probes():
    provider = StaticCapabilityProvider(
        name="identity",
        category="controller",
        items=[
            CapabilityProbe(
                name="board",
                capability="board_query",
                safety=ProbeSafety.DOCUMENTED_READ_ONLY,
                execute=lambda: make_result("board_query"),
            )
        ],
    )

    report = provider.detect(
        allowed_safety=[
            ProbeSafety.DOCUMENTED_READ_ONLY,
        ]
    )

    assert isinstance(report, CapabilityDetectionReport)
    assert report.healthy is True
    assert report.supported == 1
    assert report.results[0].capability == "board_query"


def test_static_provider_detect_preserves_probe_safety():
    provider = StaticCapabilityProvider(
        name="display",
        category="display",
        items=[
            CapabilityProbe(
                name="backlight",
                capability="backlight_control",
                safety=ProbeSafety.DOCUMENTED_STATEFUL,
                execute=lambda: make_result(
                    "backlight_control"
                ),
            )
        ],
    )

    with pytest.raises(PermissionError):
        provider.detect(
            allowed_safety=[
                ProbeSafety.DOCUMENTED_READ_ONLY,
            ]
        )


@dataclass
class ProceduralProvider:
    """Provider whose detection is not represented as probes."""

    name: str = "procedural_graphics"
    category: str = "graphics"
    calls: int = 0

    def detect(
        self,
        *,
        allowed_safety,
    ) -> CapabilityDetectionReport:
        self.calls += 1

        if ProbeSafety.EXPERIMENTAL_READ_ONLY not in set(
            allowed_safety
        ):
            raise PermissionError(
                "procedural graphics detection requires "
                "experimental_read_only authorization"
            )

        return CapabilityDetectionReport(
            results=[
                make_result(
                    "custom_glyphs",
                    ProbeOutcome.EXPERIMENTAL,
                ),
                make_result(
                    "vertical_bars",
                    ProbeOutcome.INCONCLUSIVE,
                ),
            ]
        )


def test_detector_supports_procedural_provider():
    provider = ProceduralProvider()

    detector = CapabilityProviderDetector(
        CapabilityProviderRegistry([provider])
    )

    report = detector.detect(
        allowed_safety=[
            ProbeSafety.EXPERIMENTAL_READ_ONLY,
        ]
    )

    assert provider.calls == 1
    assert len(report.providers) == 1
    assert report.experimental == 1
    assert report.inconclusive == 1


def test_procedural_provider_controls_its_own_authorization():
    provider = ProceduralProvider()

    detector = CapabilityProviderDetector(
        CapabilityProviderRegistry([provider])
    )

    with pytest.raises(PermissionError):
        detector.detect()


@dataclass
class InvalidReturnProvider:
    name: str = "invalid"
    category: str = "test"

    def detect(self, *, allowed_safety):
        return {"not": "a report"}


def test_detector_rejects_invalid_provider_return_type():
    detector = CapabilityProviderDetector(
        CapabilityProviderRegistry(
            [InvalidReturnProvider()]
        )
    )

    with pytest.raises(
        TypeError,
        match="must return CapabilityDetectionReport",
    ):
        detector.detect()


def test_registry_rejects_old_probe_only_provider():
    class OldProvider:
        name = "old"
        category = "test"

        def probes(self):
            return ()

    with pytest.raises(TypeError):
        CapabilityProviderRegistry([OldProvider()])


def test_provider_detector_still_runs_static_providers():
    provider = StaticCapabilityProvider(
        name="identity",
        category="controller",
        items=[
            CapabilityProbe(
                name="board",
                capability="board_query",
                safety=ProbeSafety.DOCUMENTED_READ_ONLY,
                execute=lambda: make_result("board_query"),
            ),
            CapabilityProbe(
                name="version",
                capability="version_query",
                safety=ProbeSafety.DOCUMENTED_READ_ONLY,
                execute=lambda: make_result("version_query"),
            ),
        ],
    )

    report = CapabilityProviderDetector(
        CapabilityProviderRegistry([provider])
    ).detect()

    assert report.healthy is True
    assert report.supported == 2
    assert {
        result.capability
        for result in report.results
    } == {
        "board_query",
        "version_query",
    }
