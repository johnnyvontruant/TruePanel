from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "truepanel" / "web" / "static"


def test_watchtower_is_served_by_additive_read_only_layer():
    server = (ROOT / "truepanel" / "web" / "watchtower_server.py").read_text()
    service = (ROOT / "truepanel" / "web" / "service.py").read_text()

    assert '"watchtower.js"' in server
    assert "<script src=\"/watchtower.js\" defer>" in server
    assert "def do_POST" not in server
    assert "from .watchtower_server import serve" in service


def test_watchtower_explains_recovery_in_plain_language():
    source = (STATIC / "watchtower.js").read_text()

    assert "Recovery tested and verified" in source
    assert "Recovery needs attention" in source
    assert "Backups exist, but recovery has not been proven." in source
    assert "Safest next action" in source
    assert "AEGIS Flight Recorder" in source
    assert "credentials, usernames, dataset paths" in source


def test_watchtower_rejects_fake_recovery_percentage():
    source = (STATIC / "watchtower.js").read_text()

    assert "deliberately not converted into a percentage" in source
    assert "missing safety gates are not partial credit" in source
    assert "required facts currently proven" in source


def test_watchtower_has_mobile_single_column_contract():
    source = (STATIC / "watchtower.js").read_text()

    assert "@media(max-width:760px)" in source
    assert ".wt-summary,.wt-gates{grid-template-columns:1fr}" in source
    assert ".wt-recorder li{grid-template-columns:1fr}" in source


def test_watchtower_hold_guidance_covers_governed_failure_classes():
    source = (STATIC / "watchtower.js").read_text()

    expected = (
        "auth\\.me",
        "write-capable",
        "missing required read-only roles",
        "receipt directory is unavailable",
        "owner does not match",
        "group- or world-writable",
        "backup task success is not a tested restore",
        "restore verification receipt is invalid",
        "stale cached evidence",
    )
    for phrase in expected:
        assert phrase in source
