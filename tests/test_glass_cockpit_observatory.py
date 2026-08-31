from pathlib import Path


ASSET = Path("truepanel/web/static/glass-cockpit.js")


def test_glass_cockpit_renders_observatory_from_shared_status_stream():
    source = ASSET.read_text(encoding="utf-8")

    assert 'window.addEventListener("truepanel:status"' in source
    assert "CURRENT ACTIVITY" in source
    assert "payload?.activity" in source
    assert "item.progress" in source
    assert "NO OBSERVED ACTIVITY" in source
    assert "ACTIVITY UNAVAILABLE" in source
    assert 'tone:"active"' in source
    assert 'tone:"idle"' in source
    assert 'tone:"unavailable"' in source
    assert "gc-activity-active" in source
    assert ".gc-activity-idle,.gc-activity-unavailable" in source
    assert "fetch(" not in source


def test_glass_cockpit_activity_preserves_mobile_and_reduced_motion_gates():
    source = ASSET.read_text(encoding="utf-8")

    assert "@media(max-width:760px)" in source
    assert ".gc-activity{padding:.75rem}" in source
    assert "@media(prefers-reduced-motion:reduce)" in source
