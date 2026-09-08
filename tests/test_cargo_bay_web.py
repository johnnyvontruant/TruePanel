from pathlib import Path

DASHBOARD = Path(
    "truepanel/web/static/index.html"
)


def source():
    return DASHBOARD.read_text(
        encoding="utf-8"
    )


def test_cargo_bay_is_final_mission_control_card():
    html = source()

    mission = html.index(
        'id="cardMissionControlStatus"'
    )
    cargo = html.index(
        'id="cardCargoBay"'
    )
    section_end = html.index(
        "</section></main>",
        cargo,
    )

    assert mission < cargo < section_end


def test_cargo_bay_has_expected_drawers():
    html = source()

    assert "Cargo Bay" in html
    assert 'id="cargoTvDrawer"' in html
    assert 'id="cargoMovieDrawer"' in html
    assert 'id="cargoDownloadDrawer"' in html
    assert 'id="cargoBackupDrawer"' in html

    assert "TV Cargo" in html
    assert "Movie Cargo" in html
    assert "Download Activity" in html
    assert "Backup Manifest" in html


def test_cargo_bay_uses_main_status_payload():
    html = source()

    assert "function renderCargoBay(cargo)" in html
    assert "renderCargoBay(data.cargo_bay);" in html

    assert "/api/v1/cargo" not in html


def test_cargo_bay_supports_all_backend_states():
    html = source()

    for state in (
        "NOMINAL",
        "CLEAR",
        "REVIEW",
        "UNAVAILABLE",
    ):
        assert f'"{state}"' in html


def test_cargo_bay_has_honest_future_placeholders():
    html = source()

    assert "Download activity reporting is not wired yet." in html
    assert "Backup tracking is not configured." in html
    assert "will not infer backup completion" in html


def test_cargo_bay_uses_safe_dom_text_rendering():
    html = source()

    assert "cargoElement(" in html
    assert "element.textContent=String(text)" in html
    assert "root.replaceChildren()" in html


def test_cargo_bay_preserves_mobile_single_column_layout():
    html = source()

    assert "@media(max-width:640px)" in html
    assert ".cargo-drawers{" in html
    assert "grid-template-columns:1fr" in html
