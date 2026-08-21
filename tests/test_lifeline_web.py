from pathlib import Path

from truepanel.web import server


def test_lifeline_asset_exists_and_is_served():
    asset = server.STATIC_DIR / "lifeline.js"
    assert asset.is_file()

    source = Path(server.__file__).read_text(encoding="utf-8")
    assert '"/lifeline.js"' in source
    assert "truepanel-lifeline" in source


def test_lifeline_cockpit_consumes_only_status_api():
    source = (server.STATIC_DIR / "lifeline.js").read_text(
        encoding="utf-8"
    )

    assert 'STATUS_URL="/api/v1/status"' in source
    assert "repair_session" in source
    assert "PLANNING ONLY" in source
    assert "Storage write authority locked" in source

    forbidden = (
        'method:"POST"',
        'method:"PUT"',
        'method:"PATCH"',
        'method:"DELETE"',
        "/api/v1/pool",
        "/api/v1/storage/replace",
        "zpool replace",
        "zpool offline",
    )
    for token in forbidden:
        assert token not in source


def test_lifeline_renders_repair_prerequisites_and_replacement_validation():
    source = (server.STATIC_DIR / "lifeline.js").read_text(
        encoding="utf-8"
    )

    assert "Repair prerequisites" in source
    assert "Replacement candidate valid" in source
    assert "Replacement candidate blocked" in source
    assert "Do not remove or replace another member" not in source
    assert "can_execute_replacement" in source


def test_lifeline_python_session_has_no_subprocess_or_storage_write_client():
    source = Path("truepanel/lifeline/session.py").read_text(encoding="utf-8")

    assert "subprocess" not in source
    assert "pool.replace" not in source
    assert "zpool" not in source
    assert "requests." not in source
