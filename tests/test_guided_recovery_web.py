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

def test_flight_manual_renders_critical_storage_guidance_as_danger():
    source = (
        server.STATIC_DIR
        / "flight-manual.js"
    ).read_text(encoding="utf-8")

    assert (
        'String(item.severity||"").toLowerCase()==="critical"'
        in source
    )
    assert 'className:critical||!exactBay?"danger":"caution"' in source
    assert "CRITICAL DRIVE HEALTH." in source
    assert 'data-guidance-severity="${esc(item.severity||"caution")}"' in source


def test_flight_manual_refresh_preserves_reader_scroll_position():
    source = (
        server.STATIC_DIR
        / "flight-manual.js"
    ).read_text(encoding="utf-8")

    assert "let renderedCards=null;" in source
    assert "const nextCards=guidance.map(card).join" in source
    assert "if(nextCards!==renderedCards)" in source
    assert "const scrollY=window.scrollY;" in source
    assert (
        "window.scrollTo(scrollX,scrollY)"
        in source
    )

    # Do not unconditionally destroy and recreate the
    # guidance DOM on every five-second status refresh.
    assert (
        'cards.innerHTML=guidance.map(card).join("");'
        not in source
    )
