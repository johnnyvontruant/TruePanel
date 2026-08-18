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


def _handler_with_json_capture():
    from truepanel.web.server import MissionControlRequestHandler

    handler = object.__new__(MissionControlRequestHandler)
    captured = []

    def capture(payload, **kwargs):
        captured.append((payload, kwargs))

    handler._json = capture
    return handler, captured


def test_preflight_handler_returns_projected_payload(monkeypatch):
    from truepanel.web import server as server_module

    handler, captured = _handler_with_json_capture()
    monkeypatch.setattr(
        server_module,
        "collect_compatibility",
        lambda: make_report(),
    )

    handler._preflight(None)

    assert captured[0][0]["flight_status"] == "READY"
    assert captured[0][0]["read_only"] is True
    assert captured[0][1] == {}


def test_support_bundle_handler_is_downloadable_and_privacy_safe(monkeypatch):
    from truepanel.compatibility.support import (
        support_bundle_contains_forbidden_keys,
    )
    from truepanel.web import server as server_module

    handler, captured = _handler_with_json_capture()
    monkeypatch.setattr(
        server_module,
        "collect_compatibility",
        lambda: make_report(),
    )

    handler._preflight_support_bundle(None)

    payload, kwargs = captured[0]
    headers = kwargs["headers"]

    assert support_bundle_contains_forbidden_keys(payload) == set()
    assert headers["Cache-Control"] == "no-store"
    assert headers["Content-Disposition"].startswith(
        'attachment; filename="truepanel-support-'
    )


def test_preflight_route_is_registered():
    from truepanel.web.server import MissionControlRequestHandler

    handler = object.__new__(MissionControlRequestHandler)
    called = []
    handler.path = "/api/v1/preflight"
    handler._preflight = lambda parsed: called.append(parsed.path)

    handler.do_GET()

    assert called == ["/api/v1/preflight"]


def test_support_bundle_route_is_registered():
    from truepanel.web.server import MissionControlRequestHandler

    handler = object.__new__(MissionControlRequestHandler)
    called = []
    handler.path = "/api/v1/preflight/support-bundle"
    handler._preflight_support_bundle = lambda parsed: called.append(parsed.path)

    handler.do_GET()

    assert called == ["/api/v1/preflight/support-bundle"]


def test_dashboard_preflight_is_on_demand_not_in_refresh_loop():
    from pathlib import Path

    source = (
        Path(__file__).parents[1]
        / "truepanel"
        / "web"
        / "static"
        / "index.html"
    ).read_text(encoding="utf-8")

    assert 'id="preflightTitle"' in source
    assert 'id="runPreflight"' in source
    assert 'href="/api/v1/preflight/support-bundle"' in source
    assert '"/api/v1/preflight"' in source
    assert "loadPreflight();" in source
    assert "setInterval(loadPreflight" not in source
    assert "setInterval(refresh,5000);" in source
    assert "replaceChildren()" in source
