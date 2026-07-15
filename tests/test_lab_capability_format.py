import json

from truepanel.lab.capabilities import (
    CapabilityDetectionReport,
    CapabilityProbeResult,
    CapabilityProviderReport,
    CapabilityProviderResult,
    ProbeOutcome,
)
from truepanel.lab.capability_format import (
    capability_report_to_json,
    render_capability_report,
)


def make_report():
    detection = CapabilityDetectionReport(
        results=[
            CapabilityProbeResult(
                capability="board_query",
                outcome=ProbeOutcome.SUPPORTED,
                detail="Board query responded",
            ),
            CapabilityProbeResult(
                capability="custom_glyphs",
                outcome=ProbeOutcome.INCONCLUSIVE,
                detail="No glyph test performed",
                successful_samples=0,
                total_samples=1,
            ),
        ]
    )

    return CapabilityProviderReport(
        providers=[
            CapabilityProviderResult(
                provider="a125_identity",
                category="controller",
                report=detection,
            )
        ]
    )


def test_human_renderer_groups_provider_results():
    output = render_capability_report(make_report())

    assert "Project Stargate Capability Report" in output
    assert "Controller" in output
    assert "Provider: A125 Identity" in output
    assert "[+] Board Query" in output
    assert "[?] Custom Glyphs" in output


def test_human_renderer_contains_summary():
    output = render_capability_report(make_report())

    assert "Providers    : 1" in output
    assert "Capabilities : 2" in output
    assert "Supported    : 1" in output
    assert "Inconclusive : 1" in output


def test_json_renderer_returns_provider_payload():
    payload = json.loads(
        capability_report_to_json(make_report())
    )

    assert payload["provider_count"] == 1
    assert payload["result_count"] == 2
    assert payload["providers"][0]["provider"] == "a125_identity"


def test_compact_json_renderer():
    output = capability_report_to_json(
        make_report(),
        indent=None,
    )

    assert "\n" not in output
