from truepanel.lab.fingerprint import (
    CapabilityState,
    ControllerFingerprint,
)
from truepanel.lab.fingerprint_builder import (
    IdentityObservation,
    StaticFingerprintProvider,
)
from truepanel.lab.service import LaboratoryService


def test_service_builds_default_a125_fingerprint():
    fingerprint = LaboratoryService().build_fingerprint()

    assert fingerprint.controller_family == "A125"
    assert fingerprint.serial_port == "/dev/ttyS1"
    assert fingerprint.baud_rate == 1200
    assert fingerprint.protocol_preamble == 0x4D


def test_service_applies_configured_providers():
    provider = StaticFingerprintProvider(
        name="configured",
        items=[
            IdentityObservation(
                board_id="0x007D",
                firmware_version="1.0",
            )
        ],
    )

    service = LaboratoryService(providers=[provider])
    fingerprint = service.build_fingerprint()

    assert fingerprint.board_id == "0x007D"
    assert fingerprint.firmware_version == "1.0"


def test_method_providers_run_after_configured_providers():
    configured = StaticFingerprintProvider(
        name="configured",
        items=[IdentityObservation(board_id="0x0001")],
    )
    runtime = StaticFingerprintProvider(
        name="runtime",
        items=[IdentityObservation(board_id="0x007D")],
    )

    service = LaboratoryService(providers=[configured])
    fingerprint = service.build_fingerprint([runtime])

    assert fingerprint.board_id == "0x007D"


def test_with_providers_returns_new_service():
    first = StaticFingerprintProvider(
        name="first",
        items=[IdentityObservation(board_id="0x0001")],
    )
    second = StaticFingerprintProvider(
        name="second",
        items=[IdentityObservation(board_id="0x007D")],
    )

    original = LaboratoryService(providers=[first])
    extended = original.with_providers([second])

    assert len(original.providers) == 1
    assert len(extended.providers) == 2
    assert extended.build_fingerprint().board_id == "0x007D"


def test_service_preserves_custom_baseline():
    baseline = ControllerFingerprint(
        controller_family="TEST",
        serial_port="/dev/test0",
        baud_rate=9600,
    )
    baseline.record_capability(
        "diagnostic_query",
        CapabilityState.EXPERIMENTAL,
    )

    fingerprint = LaboratoryService(
        baseline=baseline,
    ).build_fingerprint()

    assert fingerprint.controller_family == "TEST"
    assert fingerprint.serial_port == "/dev/test0"
    assert fingerprint.baud_rate == 9600
    assert (
        fingerprint.capabilities["diagnostic_query"].state
        is CapabilityState.EXPERIMENTAL
    )
