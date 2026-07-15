"""Presentation helpers for Stargate controller fingerprints."""

from __future__ import annotations

import json
from typing import Any

from truepanel.lab.fingerprint import (
    CapabilityState,
    ControllerFingerprint,
)


_CAPABILITY_MARKERS = {
    CapabilityState.SUPPORTED: "[+]",
    CapabilityState.UNSUPPORTED: "[-]",
    CapabilityState.EXPERIMENTAL: "[~]",
    CapabilityState.UNKNOWN: "[?]",
}


def _display_value(value: Any, fallback: str = "Unknown") -> str:
    if value is None:
        return fallback

    text = str(value).strip()
    return text if text else fallback


def _humanize_name(name: str) -> str:
    return name.replace("_", " ").strip().title()


def _format_preamble(value: int | None) -> str:
    if value is None:
        return "Unknown"

    return f"0x{value:02X}"


def _format_latency(value: float | None) -> str:
    if value is None:
        return "Unknown"

    return f"{value:.3f} ms"


def _format_confidence(value: float) -> str:
    return f"{value * 100:.1f}%"


def fingerprint_to_json(
    fingerprint: ControllerFingerprint,
    *,
    indent: int | None = 2,
) -> str:
    """Serialize a fingerprint as deterministic JSON."""

    return json.dumps(
        fingerprint.to_dict(),
        indent=indent,
        sort_keys=True,
    )


def render_fingerprint(
    fingerprint: ControllerFingerprint,
) -> str:
    """Render a fingerprint as terminal-friendly plain text."""

    lines = [
        "Project Stargate Fingerprint",
        "=" * 29,
        "",
        f"Controller : {_display_value(fingerprint.controller_family)}",
        f"Board ID   : {_display_value(fingerprint.board_id)}",
        f"Firmware   : {_display_value(fingerprint.firmware_version)}",
        "",
        "Transport",
        "---------",
        f"Port       : {_display_value(fingerprint.serial_port)}",
        f"Baud       : {_display_value(fingerprint.baud_rate)}",
        f"Preamble   : {_format_preamble(fingerprint.protocol_preamble)}",
        "",
        "Display",
        "-------",
        f"Geometry   : {_display_value(fingerprint.geometry)}",
        "",
        "Timing",
        "------",
        f"Latency    : {_format_latency(fingerprint.average_latency_ms)}",
        "",
        "Capabilities",
        "------------",
    ]

    if fingerprint.capabilities:
        for name, capability in sorted(fingerprint.capabilities.items()):
            marker = _CAPABILITY_MARKERS[capability.state]
            confidence = _format_confidence(capability.confidence)

            if capability.evidence:
                detail = f" ({confidence})"
            else:
                detail = ""

            lines.append(
                f"{marker} {_humanize_name(name)}"
                f" [{capability.state.value}]{detail}"
            )
    else:
        lines.append("None recorded")

    lines.extend(
        [
            "",
            f"Confidence : {_format_confidence(fingerprint.confidence)}",
        ]
    )

    return "\n".join(lines)
