import pytest

from truepanel.lab.capabilities import (
    CapabilityProbe,
    CapabilityProbeResult,
    CapabilityProviderDetector,
    CapabilityProviderRegistry,
    ProbeOutcome,
    ProbeSafety,
    StaticCapabilityProvider,
    provider_report_to_observations,
)
from truepanel.lab.fingerprint import CapabilityState
from truepanel.lab.fingerprint_builder import (
    FingerprintBuilder,
    StaticFingerprintProvider,
)


def make_probe(
    name,
    capability,
    *,
    outcome=ProbeOutcome.SUPPORTED,
    safety=ProbeSafety.DOCUMENTED_READ_ONLY,
):
    return CapabilityProbe(
        name=name,
        capability=capability,
        safety=safety,
        execute=lambda: CapabilityProbeResult(
            capability=capability,
            outcome=outcome,
            detail=f"{capability} detection result",
        ),
    )


def test_static_provider_normalizes_name_and_category():
    provider = StaticCapabilityProvider(
        name="Identity Provider",
        category="Controller Identity",
    )

    assert provider.name == "identity_provider"
    assert provider.category == "controller_identity"


def test_static_provider_rejects_empty_name():
    with pytest.raises(ValueError):
        StaticCapabilityProvider(
            name=" ",
            category="identity",
        )


def test_static_provider_rejects_empty_category():
    with pytest.raises(ValueError):
        StaticCapabilityProvider(
            name="identity",
            category=" ",
        )


def test_provider_registry_rejects_duplicates():
    provider = StaticCapabilityProvider(
        name="identity",
        category="identity",
    )
    registry = CapabilityProviderRegistry([provider])

    with pytest.raises(ValueError):
        registry.register(provider)


def test_provider_registry_returns_sorted_providers():
    registry = CapabilityProviderRegistry(
        [
            StaticCapabilityProvider(
                name="graphics",
                category="display",
            ),
            StaticCapabilityProvider(
                name="identity",
                category="controller",
            ),
        ]
    )

    assert [provider.name for provider in registry.all()] == [
        "graphics",
        "identity",
    ]


def test_provider_detector_runs_grouped_probes():
    provider = StaticCapabilityProvider(
        name="identity",
        category="controller",
        items=[
            make_probe("board", "board_query"),
            make_probe("version", "version_query"),
            make_probe("buttons", "button_query"),
        ],
    )

    detector = CapabilityProviderDetector(
        CapabilityProviderRegistry([provider])
    )
    report = detector.detect()

    assert report.healthy is True
    assert len(report.providers) == 1
    assert len(report.results) == 3
    assert report.supported == 3
    assert report.providers[0].provider == "identity"
    assert report.providers[0].category == "controller"


def test_provider_detector_preserves_provider_grouping():
    identity = StaticCapabilityProvider(
        name="identity",
        category="controller",
        items=[
            make_probe("board", "board_query"),
        ],
    )
    graphics = StaticCapabilityProvider(
        name="graphics",
        category="display",
        items=[
            make_probe(
                "glyphs",
                "custom_glyphs",
                outcome=ProbeOutcome.INCONCLUSIVE,
            ),
        ],
    )

    detector = CapabilityProviderDetector(
        CapabilityProviderRegistry(
            [identity, graphics]
        )
    )
    report = detector.detect()

    assert [item.provider for item in report.providers] == [
        "graphics",
        "identity",
    ]
    assert report.supported == 1
    assert report.inconclusive == 1


def test_provider_detector_can_select_specific_provider():
    identity = StaticCapabilityProvider(
        name="identity",
        category="controller",
        items=[
            make_probe("board", "board_query"),
        ],
    )
    graphics = StaticCapabilityProvider(
        name="graphics",
        category="display",
        items=[
            make_probe("glyphs", "custom_glyphs"),
        ],
    )

    detector = CapabilityProviderDetector(
        CapabilityProviderRegistry(
            [identity, graphics]
        )
    )
    report = detector.detect(
        provider_names=["identity"]
    )

    assert len(report.providers) == 1
    assert report.providers[0].provider == "identity"
    assert len(report.results) == 1


def test_provider_detector_propagates_safety_authorization():
    provider = StaticCapabilityProvider(
        name="display",
        category="display",
        items=[
            make_probe(
                "backlight",
                "backlight_control",
                safety=ProbeSafety.DOCUMENTED_STATEFUL,
            ),
        ],
    )

    detector = CapabilityProviderDetector(
        CapabilityProviderRegistry([provider])
    )

    with pytest.raises(PermissionError):
        detector.detect()

    report = detector.detect(
        allowed_safety=[
            ProbeSafety.DOCUMENTED_STATEFUL,
        ]
    )

    assert report.supported == 1


def test_provider_report_to_observations_uses_provider_source():
    provider = StaticCapabilityProvider(
        name="identity",
        category="controller",
        items=[
            make_probe("board", "board_query"),
        ],
    )

    report = CapabilityProviderDetector(
        CapabilityProviderRegistry([provider])
    ).detect()

    observations = provider_report_to_observations(report)

    assert len(observations) == 1
    assert observations[0].name == "board_query"
    assert (
        observations[0].evidence[0].source
        == "capability-provider:identity"
    )


def test_provider_observations_enrich_fingerprint():
    provider = StaticCapabilityProvider(
        name="graphics",
        category="display",
        items=[
            make_probe(
                "glyphs",
                "custom_glyphs",
                outcome=ProbeOutcome.EXPERIMENTAL,
            ),
        ],
    )

    report = CapabilityProviderDetector(
        CapabilityProviderRegistry([provider])
    ).detect()

    fingerprint_provider = StaticFingerprintProvider(
        name="capability-results",
        items=list(
            provider_report_to_observations(report)
        ),
    )

    fingerprint = FingerprintBuilder().build(
        [fingerprint_provider]
    )

    capability = fingerprint.capabilities[
        "custom_glyphs"
    ]

    assert (
        capability.state
        is CapabilityState.EXPERIMENTAL
    )
    assert capability.confidence == pytest.approx(1.0)


def test_provider_report_serialization():
    provider = StaticCapabilityProvider(
        name="identity",
        category="controller",
        items=[
            make_probe("board", "board_query"),
            make_probe(
                "version",
                "version_query",
                outcome=ProbeOutcome.UNSUPPORTED,
            ),
        ],
    )

    report = CapabilityProviderDetector(
        CapabilityProviderRegistry([provider])
    ).detect()

    payload = report.as_dict()

    assert payload["healthy"] is True
    assert payload["provider_count"] == 1
    assert payload["result_count"] == 2
    assert payload["supported"] == 1
    assert payload["unsupported"] == 1
    assert payload["providers"][0]["provider"] == "identity"
    assert payload["providers"][0]["category"] == "controller"
