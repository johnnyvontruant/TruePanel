from pathlib import Path


INDEX = (
    Path(__file__).resolve().parents[1]
    / "truepanel"
    / "web"
    / "static"
    / "index.html"
)


def source():
    return INDEX.read_text(
        encoding="utf-8"
    )


def test_cargo_bay_contains_loadmaster_drawer():
    text = source()

    assert 'id="cargoLoadmasterDrawer"' in text
    assert 'id="cargoLoadmasterSummary"' in text
    assert 'id="cargoLoadmaster"' in text


def test_loadmaster_renderer_is_wired_to_cargo_payload():
    text = source()

    assert (
        "function renderCargoLoadmaster(loadmaster)"
        in text
    )
    assert (
        "renderCargoLoadmaster("
        "\n        payload.loadmaster"
        in text
    )


def test_loadmaster_surfaces_next_cartridge():
    text = source()

    assert "NEXT CARTRIDGE" in text
    assert "Next backup:" in text
    assert "Dock this cartridge" in text
