from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "truepanel"
    / "web"
    / "static"
    / "flight-manual.js"
)


def script_text():
    return SCRIPT.read_text(encoding="utf-8")


def cockpit_function():
    text = script_text()
    return (
        text.split(
            "function installCockpitLayout(panel){",
            1,
        )[1]
        .split("function install(){", 1)[0]
    )


def test_cockpit_layout_is_progressive_enhancement():
    text = script_text()

    assert "function installCockpitLayout(panel){" in text
    assert 'document.querySelector("main .grid")' in text
    assert 'document.getElementById("cockpitOverview")' in text
    assert 'document.body.classList.add("cockpit-layout")' in text
    assert "installCockpitLayout(panel);" in text


def test_cockpit_promotes_existing_command_and_instrument_cards():
    layout = cockpit_function()

    expected = (
        'document.querySelector(".health-command")',
        'document.getElementById("healthAdvisory")',
        'document.getElementById("preflightPanel")',
        'document.getElementById("cpu")?.closest("article")',
        'document.getElementById("ram")?.closest("article")',
        'document.getElementById("network")?.closest("article")',
        'health.dataset.cockpitRole="system-health"',
        'preflight.dataset.cockpitRole="preflight"',
        'cpu.dataset.cockpitRole="cpu"',
        'memory.dataset.cockpitRole="memory"',
        'network.dataset.cockpitRole="network"',
        'commandLabel.textContent="Command Status"',
        'instrumentLabel.textContent="Live Instruments"',
    )

    for marker in expected:
        assert marker in layout


def test_cockpit_layout_does_not_touch_virtual_front_panel():
    layout = cockpit_function()

    assert "virtualLcd" not in layout
    assert "lcd-panel" not in layout
    assert "virtualLcdScreen" not in layout
    assert "virtualLcdLine1" not in layout
    assert "virtualLcdLine2" not in layout


def test_cockpit_keeps_advisory_and_flight_manual_near_command_status():
    layout = cockpit_function()

    assert "if(advisory) overview.append(advisory);" in layout
    assert "if(panel) overview.append(panel);" in layout
    assert "overview.append(instrumentLabel,instruments);" in layout


def test_cockpit_layout_has_desktop_and_mobile_compositions():
    layout = cockpit_function()

    assert ".cockpit-command-row" in layout
    assert ".cockpit-instrument-strip" in layout
    assert "grid-template-columns:minmax(0,1.2fr)" in layout
    assert "@media(max-width:980px)" in layout
    assert "@media(max-width:640px)" in layout
