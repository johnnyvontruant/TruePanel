from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "truepanel/web/static/glass-cockpit.js"


def source():
    return SOURCE.read_text()


def test_current_activity_uses_shared_status_stream_only():
    text = source()

    assert 'const ACTIVITY_ID="observatoryCurrentActivity"' in text
    assert 'window.addEventListener("truepanel:status"' in text

    block = text[text.index('const ACTIVITY_ID="observatoryCurrentActivity"'):]

    assert "fetch(" not in block
    assert "setInterval" not in block


def test_current_activity_respects_pilot_and_engineer_modes():
    text = source()

    assert (
        'body[data-mission-mode="pilot"] .observatory-engineer-detail'
        in text
    )
    assert (
        'body[data-mission-mode="engineer"] .observatory-pilot-summary'
        in text
    )
    assert 'window.TruePanelMissionMode?.setMode("engineer")' in text


def test_current_activity_preserves_neutral_idle_and_unavailable_states():
    text = source()

    assert "NO OBSERVED ACTIVITY" in text
    assert "ACTIVITY UNAVAILABLE" in text
    assert 'data-activity-state="idle"' in text
    assert 'data-activity-state="unavailable"' in text


def test_current_activity_bounds_progress_and_observations():
    text = source()

    assert "Math.max(0,Math.min(1,progress))" in text
    assert ".slice(0,8)" in text


def test_current_activity_mobile_layout_remains_single_column():
    text = source()

    assert "@media(max-width:760px)" in text
    assert ".observatory-pilot-summary," in text
    assert ".observatory-activity-item{" in text
    assert "grid-template-columns:1fr" in text
