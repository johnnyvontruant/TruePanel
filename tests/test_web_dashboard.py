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

    assert "FAN_GAUGE_MAX_RPM=2100" in source
    assert "fanGaugePercent" in source
    assert "Math.min(" in source
    assert ".fan-gauge{display:block" in source
    assert 'role="meter"' in source
    assert "calibrated range" in source


def test_dashboard_shows_calibrated_profile_targets():
    source = dashboard_source()

    assert "≈ 1,400 RPM" in source
    assert "≈ 1,550 RPM" in source
    assert "≈ 1,750 RPM" in source
    assert "≈ 1,925 RPM" in source


def test_dashboard_shows_observe_only_thermal_recommendation():
    source = dashboard_source()

    assert 'id="fanThermalRecommendation"' in source
    assert 'id="fanThermalTemperature"' in source
    assert "thermal_recommended_profile" in source
    assert "thermal_hottest_temperature_c" in source
    assert "Observe only" in source


def test_dashboard_shows_thermal_observer_history():
    source = dashboard_source()

    assert (
        "Recent Thermal Recommendations"
        in source
    )
    assert 'id="thermalHistory"' in source
    assert (
        "/api/v1/fans/"
        "thermal-history?limit=8"
        in source
    )
    assert "renderThermalHistory" in source
    assert "loadThermalHistory" in source
    assert "Telemetry unavailable" in source
    assert "Observe only" in source




def test_dashboard_has_guarded_thermal_arm_controls():
    source = (
        Path(
            "truepanel/web/static/index.html"
        ).read_text(
            encoding="utf-8"
        )
    )

    assert 'id="thermalArm"' in source
    assert 'id="thermalDisarm"' in source
    assert 'id="thermalArmState"' in source
    assert 'id="thermalActuationMode"' in source
    assert 'id="thermalArmMessage"' in source
    assert (
        "/api/v1/fans/thermal-arm"
        in source
    )


def test_dashboard_requires_thermal_arm_confirmation():
    source = (
        Path(
            "truepanel/web/static/index.html"
        ).read_text(
            encoding="utf-8"
        )
    )

    assert "ARM_THERMAL_CONTROL" in source
    assert 'requestThermalArm("arm")' not in source
    assert (
        'requestThermalArm('
        in source
    )


def test_dashboard_disarm_does_not_embed_arm_confirmation():
    source = (
        Path(
            "truepanel/web/static/index.html"
        ).read_text(
            encoding="utf-8"
        )
    )

    assert (
        'action==="arm"'
        in source
    )
    assert (
        '"Disarm thermal control and return the "'
        in source
    )
    assert (
        '"physical fans to motherboard Automatic?"'
        in source
    )


def test_dashboard_renders_runtime_thermal_arm_state():
    source = (
        Path(
            "truepanel/web/static/index.html"
        ).read_text(
            encoding="utf-8"
        )
    )

    assert (
        "thermal_operator_armed"
        in source
    )
    assert (
        "thermal_dry_run"
        in source
    )
    assert (
        "thermal_policy_mode"
        in source
    )
    assert (
        "renderThermalArmControls(data)"
        in source
    )



def test_dashboard_has_supervised_live_control():
    source = Path(
        "truepanel/web/static/index.html"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        'id="thermalSupervisedLive"'
        in source
    )
    assert (
        'id="thermalLeaseState"'
        in source
    )
    assert (
        "Balanced only · 120 seconds"
        in source
    )


def test_dashboard_requires_stronger_live_confirmation():
    source = Path(
        "truepanel/web/static/index.html"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "ENGAGE_SUPERVISED_THERMAL_CONTROL"
        in source
    )
    assert (
        'action==="supervised_live"'
        in source
    )
    assert (
        '"supervised_live"'
        in source
    )


def test_dashboard_live_button_requires_balanced_automatic_start():
    source = Path(
        "truepanel/web/static/index.html"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        'recommendation==="balanced"'
        in source
    )
    assert (
        'activeProfile==="automatic"'
        in source
    )
    assert (
        "!safetyHold"
        in source
    )
    assert (
        "!recoveryPending"
        in source
    )


def test_dashboard_renders_supervised_lease_countdown():
    source = Path(
        "truepanel/web/static/index.html"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "thermal_supervised_session_active"
        in source
    )
    assert (
        "thermal_supervised_session_remaining"
        in source
    )
    assert (
        "seconds remaining"
        in source
    )



def test_dashboard_renders_commissioning_state():
    source = Path(
        "truepanel/web/static/index.html"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        'id="thermalCommissioningState"'
        in source
    )
    assert (
        "thermal_commissioning_state"
        in source
    )
    assert (
        "function thermalCommissioningLabel"
        in source
    )
    assert "Configured" in source
    assert "Dry-run armed" in source
    assert "Supervised live" in source
    assert "Commissioned · Disarmed" in source



def test_dashboard_shows_commissioning_history():
    source = dashboard_source()

    assert (
        "Recent Commissioning Activity"
        in source
    )
    assert (
        'id="commissioningHistory"'
        in source
    )
    assert (
        "/api/v1/fans/"
        "commissioning-history?limit=8"
        in source
    )
    assert (
        "renderCommissioningHistory"
        in source
    )
    assert (
        "loadCommissioningHistory"
        in source
    )
    assert (
        "Supervised session started"
        in source
    )
    assert "Manually disarmed" in source
    assert "Lease expired" in source
    assert "Safety cancellation" in source


def test_dashboard_has_bounded_automatic_controls():
    source = Path(
        "truepanel/web/static/index.html"
    ).read_text(
        encoding="utf-8"
    )

    assert 'id="thermalAutomaticLease"' in source
    assert 'id="thermalCancelAutomatic"' in source
    assert 'id="thermalAutomaticLeaseState"' in source
    assert 'id="thermalFingerprintState"' in source
    assert 'id="thermalAutomaticEnvelope"' in source

    assert "thermal_automatic_lease_active" in source
    assert "thermal_automatic_lease_remaining" in source
    assert (
        "thermal_commissioned_fingerprint_match"
        in source
    )
    assert (
        "thermal_automatic_allowed_profiles"
        in source
    )

    assert (
        "ENGAGE_STAGE_3_AUTOMATIC_CONTROL"
        in source
    )
    assert (
        'requestThermalArm(\n'
        '        "automatic_lease"'
        in source
    )


def test_dashboard_has_stage_three_renewal_controls():
    source = Path(
        "truepanel/web/static/index.html"
    ).read_text(
        encoding="utf-8"
    )

    assert 'id="thermalRenewAutomatic"' in source
    assert (
        'id="thermalAutomaticLeaseExpires"'
        in source
    )
    assert "24 hours" in source
    assert (
        "ENGAGE_STAGE_3_AUTOMATIC_CONTROL"
        in source
    )
    assert (
        "RENEW_STAGE_3_AUTOMATIC_CONTROL"
        in source
    )
    assert (
        'requestThermalArm(\n'
        '        "automatic_lease_renew"'
        in source
    )
    assert "automaticRenewAllowed" in source
    assert "toLocaleString()" in source


def test_dashboard_contains_virtual_lcd_faceplate():
    source = dashboard_source()

    for element_id in (
        "virtualLcdScreen",
        "virtualLcdLine1",
        "virtualLcdLine2",
        "virtualLcdState",
        "virtualLcdPage",
        "virtualLcdAge",
        "virtualLcdEnter",
        "virtualLcdSelect",
        "virtualLcdMessage",
    ):
        assert (
            f'id="{element_id}"'
            in source
        )


def test_virtual_lcd_uses_lightweight_status_route():
    source = dashboard_source()

    assert '"/api/v1/lcd"' in source
    assert (
        '"/api/v1/lcd/button"'
        in source
    )
    assert "refreshVirtualLcd" in source
    assert "setInterval(refreshVirtualLcd,1000)" in source


def test_virtual_lcd_buttons_are_guarded():
    source = dashboard_source()

    assert (
        'button:buttonName'
        in source
    )
    assert (
        'virtualLcdRequestInFlight'
        in source
    )
    assert (
        'q("virtualLcdEnter").disabled'
        in source
    )
    assert (
        'q("virtualLcdSelect").disabled'
        in source
    )


def test_virtual_lcd_preserves_fixed_width_text():
    source = dashboard_source()

    assert (
        'padEnd(16," ")'
        in source
    )
    assert "white-space:pre" in source
    assert "width:16ch" in source


def test_dashboard_contains_lcd_transport_diagnostics():
    source = dashboard_source()

    for element_id in (
        "lcdTransportConnection",
        "lcdTransportPort",
        "lcdTransportSpeed",
        "lcdTransportReader",
        "lcdTransportDispatcher",
        "lcdTransportErrors",
        "lcdTransportLastError",
        "lcdTransportAge",
    ):
        assert (
            f'id="{element_id}"'
            in source
        )

    assert "LCD Transport" in source


def test_lcd_transport_diagnostics_use_reader_payload():
    source = dashboard_source()

    for field in (
        "reader.connected",
        "reader.port",
        "reader.speed",
        "reader.thread_alive",
        "reader.dispatcher_alive",
        "reader.reader_errors",
        "reader.connection_error",
        "reader.last_reader_error",
        "lcd.age_seconds",
    ):
        assert field in source


def test_lcd_transport_diagnostics_have_explicit_states():
    source = dashboard_source()

    for label in (
        "Connected",
        "Disconnected",
        "Running",
        "Stopped",
        "Unavailable",
        "None",
    ):
        assert label in source

    assert '?"warn"' in source
    assert '?"bad"' in source
    assert '?"good"' in source
