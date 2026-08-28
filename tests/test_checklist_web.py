from pathlib import Path

from truepanel.web import server


def test_checklist_cockpit_renders_from_read_only_status_payload():
    source = (server.STATIC_DIR / "lifeline.js").read_text(
        encoding="utf-8"
    )

    assert 'STATUS_URL="/api/v1/status"' in source
    assert "operator_checklists" in source
    assert "PROJECT CHECKLIST" in source
    assert "CHECKLIST STATUS" in source
    assert "MACHINE VERIFIED" in source
    assert "AUTHORITY HOLD" in source
    assert "data-checklist-state" in source


def test_checklist_cockpit_never_exposes_manual_pass_or_storage_execution():
    source = (server.STATIC_DIR / "lifeline.js").read_text(
        encoding="utf-8"
    )

    assert "No manual PASS or Resolve controls" in source
    assert "Human actions are never auto-marked complete." in source
    assert "Destructive storage execution is not available" in source
    assert "can_execute_replacement" in source

    forbidden = (
        'method:"POST"',
        'method:"PUT"',
        'method:"PATCH"',
        'method:"DELETE"',
        "/api/v1/pool",
        "/api/v1/storage/replace",
        "zpool replace",
        "zpool offline",
        "Mark complete",
        "Mark PASS",
        "Resolve fault",
    )
    for token in forbidden:
        assert token not in source


def test_checklist_reuses_existing_flight_manual_and_lifeline_surface():
    source = (server.STATIC_DIR / "lifeline.js").read_text(
        encoding="utf-8"
    )
    server_source = Path(server.__file__).read_text(encoding="utf-8")

    assert 'getElementById("flightManualPanel")' in source
    assert '.fm-card[data-guidance-code]' in source
    assert '"/lifeline.js"' in server_source
    assert "truepanel-lifeline" in server_source


def test_checklist_mobile_layout_collapses_to_single_column():
    source = (server.STATIC_DIR / "lifeline.js").read_text(
        encoding="utf-8"
    )

    assert "@media(max-width:760px)" in source
    assert ".cl-mission-rail,.cl-grid{grid-template-columns:1fr}" in source
    assert ".cl-status-rail,.cl-head{display:block}" in source


def test_checklist_procedure_sections_are_expandable_without_completion_buttons():
    source = (server.STATIC_DIR / "lifeline.js").read_text(
        encoding="utf-8"
    )

    assert '<details class="cl-procedure"' in source
    assert "checklistSections" in source
    assert "checklistPreflight" in source
    assert "checklistCapabilities" in source
