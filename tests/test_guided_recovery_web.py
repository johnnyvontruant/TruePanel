from pathlib import Path

from truepanel.web import server


def test_flight_manual_asset_exists_and_is_served_by_extension():
    asset = server.STATIC_DIR / "flight-manual.js"
    assert asset.is_file()

    source = Path(server.__file__).read_text(encoding="utf-8")
    assert '"/flight-manual.js"' in source
    assert "truepanel-flight-manual" in source


def test_flight_manual_consumes_only_read_only_status_api():
    source = (server.STATIC_DIR / "flight-manual.js").read_text(
        encoding="utf-8"
    )

    assert 'STATUS_URL="/api/v1/status"' in source
    assert "operator_guidance" in source
    assert "DESTRUCTIVE · LOCKED" in source
    assert "DO NOT REMOVE A DISK" in source

    forbidden = (
        "/api/v1/fans/profile",
        "/api/v1/fans/thermal-arm",
        "/api/v1/lcd/button",
        "/api/v1/config/night-mode/save",
        'method:"POST"',
        'method:"PUT"',
        'method:"PATCH"',
        'method:"DELETE"',
    )
    for token in forbidden:
        assert token not in source


def test_existing_flight_manual_button_is_the_ui_entry_point():
    dashboard = (server.STATIC_DIR / "index.html").read_text(
        encoding="utf-8"
    )
    manual = (server.STATIC_DIR / "flight-manual.js").read_text(
        encoding="utf-8"
    )

    assert 'id="openFlightManual"' in dashboard
    assert 'getElementById("openFlightManual")' in manual
    assert "physical_service_ready" in manual
    assert "destructive_actions_ready" in manual
