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

    for profile in (
        "automatic",
        "quiet",
        "balanced",
        "cooling_boost",
        "afterburners",
    ):
        assert (
            f'data-fan-profile="{profile}"'
            in source
        )

    assert "selectFanProfile(" in source
    assert "requestFanProfile(" in source
    assert "ENGAGE_AFTERBURNERS" in source


def test_dashboard_preserves_direct_hardware_boundary():
    source = dashboard_source()

    assert "Direct hardware access" in source
    assert "Guarded socket only" in source
    assert "/sys/" not in source
    assert "pwm1_enable" not in source
    assert "pwm2_enable" not in source


def test_dashboard_shows_afterburners_countdown():
    source = dashboard_source()

    assert 'id="fanControlCountdown"' in source
    assert "remaining_seconds" in source
    assert "remaining" in source
    assert "automatically restore" in source


def test_dashboard_shows_fan_control_history():
    source = dashboard_source()

    assert 'id="fanHistory"' in source
    assert "Recent Fan Activity" in source
    assert "/api/v1/fans/history?limit=8" in source
    assert "renderFanHistory" in source
    assert "Automatic restore" in source
    assert "Safety escalation" in source

def test_dashboard_uses_measured_fan_rpm_scale():
    source = dashboard_source()

    assert "FAN_GAUGE_MAX_RPM=2000" in source
    assert "fanGaugePercent" in source
    assert "Math.min(" in source
    assert 'role="meter"' in source
    assert "calibrated range" in source


def test_dashboard_shows_calibrated_profile_targets():
    source = dashboard_source()

    assert "≈ 1,400 RPM" in source
    assert "≈ 1,550 RPM" in source
    assert "≈ 1,750 RPM" in source
    assert "≈ 1,950 RPM" in source
