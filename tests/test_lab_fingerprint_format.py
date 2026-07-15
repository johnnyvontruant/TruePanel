import json

from truepanel.lab.fingerprint import (
    CapabilityState,
    ControllerFingerprint,
    FingerprintEvidence,
)
from truepanel.lab.fingerprint_format import (
    fingerprint_to_json,
    render_fingerprint,
)


def test_renderer_contains_identity_and_transport():
    fingerprint = ControllerFingerprint(
        controller_family="A125",
        board_id="0x007D",
        firmware_version="1.0",
        serial_port="/dev/ttyS1",
        baud_rate=1200,
        protocol_preamble=0x4D,
    )

    output = render_fingerprint(fingerprint)

    assert "Project Stargate Fingerprint" in output
    assert "Controller : A125" in output
    assert "Board ID   : 0x007D" in output
    assert "Firmware   : 1.0" in output
    assert "Port       : /dev/ttyS1" in output
    assert "Baud       : 1200" in output
    assert "Preamble   : 0x4D" in output


def test_renderer_displays_unknown_values():
    fingerprint = ControllerFingerprint(controller_family="A125")

    output = render_fingerprint(fingerprint)

    assert "Board ID   : Unknown" in output
    assert "Firmware   : Unknown" in output
    assert "Geometry   : Unknown" in output
    assert "Latency    : Unknown" in output


def test_renderer_displays_geometry_and_latency():
    fingerprint = ControllerFingerprint(
        controller_family="A125",
        display_columns=16,
        display_rows=2,
        average_latency_ms=50.48,
    )

    output = render_fingerprint(fingerprint)

    assert "Geometry   : 16x2" in output
    assert "Latency    : 50.480 ms" in output


def test_renderer_displays_capability_states():
    fingerprint = ControllerFingerprint(controller_family="A125")

    fingerprint.record_capability(
        "board_query",
        CapabilityState.SUPPORTED,
    )
    fingerprint.record_capability(
        "graphics",
        CapabilityState.UNKNOWN,
    )
    fingerprint.record_capability(
        "custom_glyphs",
        CapabilityState.EXPERIMENTAL,
    )
    fingerprint.record_capability(
        "dangerous_opcode",
        CapabilityState.UNSUPPORTED,
    )

    output = render_fingerprint(fingerprint)

    assert "[+] Board Query [supported]" in output
    assert "[?] Graphics [unknown]" in output
    assert "[~] Custom Glyphs [experimental]" in output
    assert "[-] Dangerous Opcode [unsupported]" in output


def test_renderer_displays_evidence_confidence():
    fingerprint = ControllerFingerprint(controller_family="A125")

    fingerprint.record_capability(
        "board_query",
        CapabilityState.SUPPORTED,
        evidence=[
            FingerprintEvidence(
                source="repeat",
                observation="consistent response",
                successful_samples=24,
                total_samples=25,
            )
        ],
    )

    output = render_fingerprint(fingerprint)

    assert "[+] Board Query [supported] (96.0%)" in output
    assert "Confidence : 96.0%" in output


def test_json_renderer_returns_valid_deterministic_payload():
    fingerprint = ControllerFingerprint(
        controller_family="A125",
        board_id="0x007D",
        serial_port="/dev/ttyS1",
        baud_rate=1200,
        protocol_preamble=0x4D,
    )

    first = fingerprint_to_json(fingerprint)
    second = fingerprint_to_json(fingerprint)
    payload = json.loads(first)

    assert first == second
    assert payload["controller_family"] == "A125"
    assert payload["board_id"] == "0x007D"
    assert payload["transport"]["serial_port"] == "/dev/ttyS1"
    assert payload["transport"]["protocol_preamble"] == 0x4D


def test_compact_json_renderer():
    fingerprint = ControllerFingerprint(controller_family="A125")

    output = fingerprint_to_json(fingerprint, indent=None)

    assert "\n" not in output
    assert json.loads(output)["controller_family"] == "A125"
