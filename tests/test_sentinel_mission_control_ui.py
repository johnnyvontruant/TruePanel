from pathlib import Path


ASSET = Path("truepanel/web/static/glass-cockpit.js")


def _source() -> str:
    return ASSET.read_text(encoding="utf-8")


def test_sentinel_card_uses_live_explanation_contract():
    source = _source()

    for token in (
        "sentinelFlightDirector",
        "sentinel?.explanations",
        "Flight Director",
        "known_impact",
        "protected_items",
        "unknowns",
        "language_guard",
        "Evidence, provenance, and recovery references",
    ):
        assert token in source


def test_sentinel_standby_copy_is_not_an_all_clear_claim():
    source = _source()

    assert "The evidence engine is standing by." in source
    assert "This is not an all-clear assertion." in source
    assert "No active SENTINEL impact explanation is available." in source


def test_sentinel_ui_preserves_provenance_and_mobile_layout():
    source = _source()

    assert 'path.join(" → ")' in source
    assert "sentinel-path" in source
    assert "@media(max-width:760px)" in source
    assert "@media(max-width:480px)" in source
    assert "min-height:44px" in source
    assert "overflow-wrap:anywhere" in source


def test_sentinel_card_exposes_pathfinder_as_reference_only():
    source = _source()

    for token in (
        "Pathfinder recovery references",
        "Reference only · no repair authority",
        "physical_service_ready",
        "destructive_actions_ready",
        "Blocked by:",
        "recovery?.references",
    ):
        assert token in source


def test_sentinel_card_does_not_offer_recovery_actuation():
    source = _source()

    forbidden = (
        "Execute recovery",
        "Run recovery",
        "Apply fix",
        "Replace disk now",
    )
    assert all(token not in source for token in forbidden)
