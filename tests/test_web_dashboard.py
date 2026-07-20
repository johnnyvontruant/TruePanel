from pathlib import Path


def dashboard_source():
    return Path(
        "truepanel/web/static/index.html"
    ).read_text(
        encoding="utf-8",
    )


def test_dashboard_contract():
    source = dashboard_source()

    assert "TruePanel Mission Control" in source
    assert "/api/v1/status" in source
    assert "setInterval(refresh,5000)" in source
    assert "Hardware writes" in source


def test_dashboard_has_night_mode_controls():
    source = dashboard_source()

    assert "Night Mode Configuration" in source
    assert 'id="idleAfter"' in source
    assert 'id="rotationInterval"' in source
    assert 'id="nightEnabled"' in source
    assert 'id="suppressInfo"' in source
    assert 'id="backlightOff"' in source
    assert 'id="wakeOnButton"' in source


def test_dashboard_uses_guarded_policy_endpoints():
    source = dashboard_source()

    assert "/api/v1/config/night-mode" in source
    assert "/api/v1/config/night-mode/preview" in source
    assert "/api/v1/config/night-mode/save" in source
    assert "writes_enabled" in source
    assert "--allow-config-writes" in source


def test_dashboard_requires_confirmation_before_save():
    source = dashboard_source()

    assert "confirm(" in source
    assert "Manual TruePanel restart required" in source


def test_dashboard_preserves_hardware_write_lock():
    source = dashboard_source()

    assert "Hardware writes" in source
    assert ">Disabled<" in source
