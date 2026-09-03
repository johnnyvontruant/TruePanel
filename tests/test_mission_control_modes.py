from pathlib import Path

from truepanel.web import server


def _source() -> str:
    return (server.STATIC_DIR / "glass-cockpit.js").read_text(encoding="utf-8")


def test_glass_cockpit_asset_is_served_by_extension():
    asset = server.STATIC_DIR / "glass-cockpit.js"
    assert asset.is_file()

    source = Path(server.__file__).read_text(encoding="utf-8")
    assert '"/glass-cockpit.js"' in source
    assert "truepanel-glass-cockpit" in source


def test_mission_modes_default_to_pilot_and_persist_locally():
    source = _source()

    assert 'MISSION_MODE_KEY="truepanel.mission.mode.v1"' in source
    assert 'const PILOT="pilot";' in source
    assert 'const ENGINEER="engineer";' in source
    assert 'return value===ENGINEER?ENGINEER:PILOT;' in source
    assert "window.localStorage.getItem(MISSION_MODE_KEY)" in source
    assert "window.localStorage.setItem(MISSION_MODE_KEY,mode)" in source


def test_pilot_mode_keeps_deep_diagnostics_out_of_the_day_to_day_view():
    source = _source()

    hidden_in_pilot = (
        '.temps-card',
        '.fans-card',
        '.events-card',
        '#aegisReliabilityView',
        '#cockpitMaintenance',
        '#openFlightManual',
        '#flightManualPanel',
        '.cockpit-layout-switcher',
        '#glassCockpitSituation>details',
    )
    for selector in hidden_in_pilot:
        assert f'body[data-mission-mode="pilot"] {selector}' in source

    assert 'modeButton(PILOT,"Pilot"' in source
    assert 'modeButton(ENGINEER,"Engineer"' in source
    assert "Flight Engineer Mode" in source


def test_mission_mode_switch_is_presentation_only():
    source = _source()
    mode_source = source[source.index('const MISSION_MODE_KEY='):]

    assert "fetch(" not in mode_source
    assert "XMLHttpRequest" not in mode_source
    assert 'method:"POST"' not in mode_source
    assert 'method:"PUT"' not in mode_source
    assert 'method:"PATCH"' not in mode_source
    assert 'method:"DELETE"' not in mode_source
    assert 'document.body.dataset.missionMode=mode' in mode_source
    assert 'CustomEvent("truepanel:mission-mode"' in mode_source


def test_mission_mode_switch_preserves_mobile_and_accessibility_contracts():
    source = _source()

    assert 'role","group"' in source
    assert 'aria-label","Mission Control operating mode"' in source
    assert 'aria-pressed' in source
    assert '@media(max-width:640px)' in source
    assert "min-height:40px" in source
