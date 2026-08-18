from truepanel.compatibility.models import CompatibilityCheck, CompatibilityReport
from truepanel.web.preflight import build_preflight_payload


def make_report(*, classification="SUPPORTED"):
    return CompatibilityReport(
        classification=classification,
        installation_mode="OBSERVATION ONLY",
        hardware_control="LOCKED - COMMISSIONING REQUIRED",
        checks=(
            CompatibilityCheck("PASS", "TrueNAS SCALE", "25.10.5"),
            CompatibilityCheck("PASS", "Architecture", "x86_64"),
            CompatibilityCheck("REVIEW", "QNAP Identity", "QW56"),
            CompatibilityCheck("PASS", "Fan Controller", "Fintek"),
            CompatibilityCheck("PASS", "Fan Telemetry", "fan1 fan2"),
            CompatibilityCheck("PASS", "PWM Interfaces", "pwm1 pwm2"),
            CompatibilityCheck("PASS", "Enclosure Topology", "6 slots"),
            CompatibilityCheck("PASS", "Storage Safety", "passive only"),
            CompatibilityCheck("PASS", "Front Panel Serial", "/dev/ttyS1"),
            CompatibilityCheck("PASS", "Safety Authority", "locked"),
        ),
    )


def test_supported_preflight_is_ready_but_preserves_review_checks():
    payload = build_preflight_payload(make_report())

    assert payload["schema_version"] == 1
    assert payload["read_only"] is True
    assert payload["flight_status"] == "READY"
    assert payload["counts"] == {
        "pass": 9,
        "review": 1,
        "fail": 0,
    }
    assert payload["installation_mode"] == "OBSERVATION ONLY"
    assert payload["hardware_control"] == "LOCKED - COMMISSIONING REQUIRED"

    sections = {
        section["id"]: section
        for section in payload["sections"]
    }

    assert sections["host"]["status"] == "REVIEW"
    assert sections["cooling"]["status"] == "PASS"
    assert sections["storage"]["status"] == "PASS"
    assert sections["front-panel"]["status"] == "PASS"
    assert sections["safety"]["status"] == "PASS"


def test_partial_preflight_requires_review():
    payload = build_preflight_payload(
        make_report(classification="PARTIAL")
    )

    assert payload["flight_status"] == "REVIEW"
    assert "operator review" in payload["summary"].lower()


def test_unsupported_preflight_holds():
    payload = build_preflight_payload(
        make_report(classification="UNSUPPORTED")
    )

    assert payload["flight_status"] == "HOLD"


def test_unknown_checks_remain_visible_in_host_section():
    report = CompatibilityReport(
        classification="REVIEW",
        installation_mode="OBSERVATION ONLY",
        hardware_control="LOCKED - COMMISSIONING REQUIRED",
        checks=(
            CompatibilityCheck(
                "REVIEW",
                "Future Compatibility Probe",
                "new signal",
            ),
        ),
    )

    payload = build_preflight_payload(report)
    host = next(
        section
        for section in payload["sections"]
        if section["id"] == "host"
    )

    assert host["checks"][0]["name"] == "Future Compatibility Probe"
