"""Terminal and JSON rendering for Stargate capability reports."""

from __future__ import annotations

import json

from truepanel.lab.capabilities import (
    CapabilityProviderReport,
    ProbeOutcome,
)


_OUTCOME_MARKERS = {
    ProbeOutcome.SUPPORTED: "[+]",
    ProbeOutcome.UNSUPPORTED: "[-]",
    ProbeOutcome.EXPERIMENTAL: "[~]",
    ProbeOutcome.INCONCLUSIVE: "[?]",
    ProbeOutcome.ERROR: "[!]",
}


def _humanize(value: str) -> str:
    return value.replace("_", " ").strip().title()


def capability_report_to_json(
    report: CapabilityProviderReport,
    *,
    indent: int | None = 2,
) -> str:
    """Serialize a capability-provider report deterministically."""

    return json.dumps(
        report.as_dict(),
        indent=indent,
        sort_keys=True,
    )


def render_capability_report(
    report: CapabilityProviderReport,
) -> str:
    """Render a grouped terminal-friendly capability report."""

    lines = [
        "Project Stargate Capability Report",
        "=" * 35,
    ]

    if not report.providers:
        lines.extend(
            [
                "",
                "No capability providers registered.",
            ]
        )
    else:
        for provider in report.providers:
            lines.extend(
                [
                    "",
                    _humanize(provider.category),
                    "-" * len(_humanize(provider.category)),
                    f"Provider: {_humanize(provider.provider)}",
                    "",
                ]
            )

            if not provider.report.results:
                lines.append("  No capability results")
                continue

            for result in provider.report.results:
                marker = _OUTCOME_MARKERS[result.outcome]
                confidence = result.confidence * 100.0

                lines.append(
                    f"{marker} "
                    f"{_humanize(result.capability):<24} "
                    f"{result.outcome.value:<12} "
                    f"{confidence:5.1f}%"
                )

    lines.extend(
        [
            "",
            "Summary",
            "-------",
            f"Providers    : {len(report.providers)}",
            f"Capabilities : {len(report.results)}",
            f"Supported    : {report.supported}",
            f"Unsupported  : {report.unsupported}",
            f"Experimental : {report.experimental}",
            f"Inconclusive : {report.inconclusive}",
            f"Status       : {'PASS' if report.healthy else 'ATTENTION'}",
        ]
    )

    return "\n".join(lines)
