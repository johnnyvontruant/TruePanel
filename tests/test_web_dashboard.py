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
    assert "Direct hardware access" in source
    assert "Guarded socket only" in source


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

    assert "Direct hardware access" in source
    assert ">Disabled<" in source
    assert "Guarded socket only" in source


def test_dashboard_has_guarded_fan_controls():
    source = dashboard_source()

    assert 'id="fanAutomatic"' in source
    assert 'id="fanAfterburners"' in source
    assert 'id="fanActiveProfile"' in source
    assert 'id="fanControlConnection"' in source
    assert "/api/v1/fans/profile" in source


def test_dashboard_requires_afterburners_confirmation():
    source = dashboard_source()

    assert "ENGAGE AFTERBURNERS?" in source
    assert "ENGAGE_AFTERBURNERS" in source
    assert 'requestFanProfile(' in source


def test_dashboard_exposes_only_safe_profiles():
    source = dashboard_source()

    assert 'requestFanProfile("automatic")' in source
    assert '"afterburners",' in source

    assert 'requestFanProfile("quiet")' not in source
    assert 'requestFanProfile("balanced")' not in source
    assert 'requestFanProfile("cooling_boost")' not in source


def test_dashboard_preserves_direct_hardware_boundary():
    source = dashboard_source()

    assert "Direct hardware access" in source
    assert "Guarded socket only" in source
    assert "/sys/" not in source
    assert "pwm1_enable" not in source
    assert "pwm2_enable" not in source
