from dataclasses import dataclass

from truepanel.host import (
    HostAgentCapabilities,
    HostCapability,
    capabilities_from_compatibility,
)


@dataclass
class FakeCheck:
    status: str
    name: str
    detail: str


@dataclass
class FakeReport:
    classification: str
    checks: list[FakeCheck]


def make_report(
    *,
    classification="SUPPORTED",
    lcd="PASS",
    fans="PASS",
    pwm="PASS",
    enclosure="PASS",
):
    return FakeReport(
        classification=classification,
        checks=[
            FakeCheck(
                lcd,
                "Front Panel Serial",
                "serial interface",
            ),
            FakeCheck(
                fans,
                "Fan Telemetry",
                "fan inputs",
            ),
            FakeCheck(
                pwm,
                "PWM Interfaces",
                "PWM interfaces",
            ),
            FakeCheck(
                enclosure,
                "Enclosure Topology",
                "enclosure interface",
            ),
            FakeCheck(
                "PASS",
                "Safety Authority",
                "hardware control remains locked",
            ),
        ],
    )


def test_capability_model_defaults_to_no_authority():
    capability = HostCapability(
        available=True,
        detail="detected",
    )

    assert capability.available is True
    assert capability.authorized is False


def test_supported_host_builds_passive_manifest():
    manifest = capabilities_from_compatibility(
        make_report()
    )

    assert isinstance(
        manifest,
        HostAgentCapabilities,
    )

    assert manifest.platform.available is True
    assert manifest.lcd.available is True
    assert manifest.fan_telemetry.available is True
    assert manifest.fan_control.available is True
    assert manifest.enclosure.available is True

    assert manifest.hardware_authority_granted is False


def test_pwm_discovery_never_grants_fan_authority():
    manifest = capabilities_from_compatibility(
        make_report(
            pwm="PASS",
        )
    )

    assert manifest.fan_control.available is True
    assert manifest.fan_control.authorized is False
    assert manifest.hardware_authority_granted is False


def test_partial_capabilities_are_reported_independently():
    manifest = capabilities_from_compatibility(
        make_report(
            classification="PARTIAL",
            lcd="REVIEW",
            fans="PASS",
            pwm="REVIEW",
            enclosure="PASS",
        )
    )

    assert manifest.platform.available is True
    assert manifest.lcd.available is False
    assert manifest.fan_telemetry.available is True
    assert manifest.fan_control.available is False
    assert manifest.enclosure.available is True


def test_unsupported_platform_is_not_agent_ready():
    manifest = capabilities_from_compatibility(
        make_report(
            classification="UNSUPPORTED",
        )
    )

    assert manifest.platform.available is False
    assert manifest.hardware_authority_granted is False


def test_missing_check_fails_closed():
    report = FakeReport(
        classification="SUPPORTED",
        checks=[],
    )

    manifest = capabilities_from_compatibility(
        report
    )

    assert manifest.lcd.available is False
    assert manifest.fan_telemetry.available is False
    assert manifest.fan_control.available is False
    assert manifest.enclosure.available is False
    assert manifest.hardware_authority_granted is False


def test_manifest_serializes_to_stable_dictionary():
    payload = capabilities_from_compatibility(
        make_report()
    ).to_dict()

    assert payload["host_agent"] == {
        "available": True,
        "hardware_authority_granted": False,
    }

    assert payload["capabilities"]["lcd"]["available"] is True
    assert payload["capabilities"]["lcd"]["authorized"] is False

    assert (
        payload["capabilities"]["fan_control"]["available"]
        is True
    )
    assert (
        payload["capabilities"]["fan_control"]["authorized"]
        is False
    )


def test_capability_manifest_does_not_mutate_source_report():
    report = make_report()

    before = list(report.checks)

    capabilities_from_compatibility(report)

    assert report.checks == before
