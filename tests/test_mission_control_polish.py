from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "truepanel"
    / "web"
    / "static"
    / "cockpit-polish.js"
)


def text():
    return SCRIPT.read_text(encoding="utf-8")


def test_polish_layer_is_read_only_dom_enhancement():
    script = text()

    assert "fetch(" not in script
    assert 'method:"POST"' not in script
    assert 'method:"PUT"' not in script
    assert 'method:"PATCH"' not in script
    assert 'method:"DELETE"' not in script
    assert "XMLHttpRequest" not in script


def test_polish_collapses_lcd_transport_without_touching_vfp_display():
    script = text()

    assert 'document.querySelector(".lcd-transport")' in script
    assert 'id:"cockpitLcdTransport"' in script
    assert 'title:"LCD Transport"' in script
    assert "virtualLcdScreen" not in script
    assert "virtualLcdLine1" not in script
    assert "virtualLcdLine2" not in script
    assert "lcd-faceplate" not in script
    assert "lcd-screen" not in script
    assert "lcd-rocker" not in script


def test_polish_collapses_controls_but_leaves_operational_cooling_visible():
    script = text()

    assert 'document.getElementById("fanControlConnection")' in script
    assert 'closest(".control-panel")' in script
    assert 'id:"cockpitCoolingControls"' in script
    assert 'title:"Controls & Automation"' in script
    assert "fanActiveProfile" in script
    assert "fanThermalRecommendation" in script
    assert 'document.getElementById("fans")' not in script
    assert 'document.getElementById("fanThermalTemperature")' not in script


def test_preflight_review_cards_have_direct_path_to_details():
    script = text()

    assert 'document.getElementById("preflightSections")' in script
    assert 'document.getElementById("preflightDetails")' in script
    assert 'textContent||""' in script
    assert '==="REVIEW"' in script
    assert 'card.dataset.cockpitReview="true"' in script
    assert 'card.setAttribute("role","button")' in script
    assert 'card.tabIndex=0' in script
    assert '"Review details →"' in script
    assert "details.open=true" in script
    assert 'group.scrollIntoView({behavior:"smooth",block:"center"})' in script


def test_preflight_review_navigation_does_not_fake_review_as_pass():
    script = text()

    assert 'status?.textContent' in script
    assert 'textContent="PASS"' not in script
    assert 'textContent="READY"' not in script
    assert "acknowledge" not in script.lower()


def test_footer_drops_stale_hard_coded_version():
    script = text()

    assert 'footer.textContent="TruePanel Mission Control"' in script
    assert "v1.1" not in script


def test_drawer_summaries_keep_health_state_visible_while_closed():
    script = text()

    assert 'document.getElementById("lcdTransportConnection")' in script
    assert 'document.getElementById("lcdTransportReader")' in script
    assert 'document.getElementById("lcdTransportDispatcher")' in script
    assert 'text:"Healthy",tone:"good"' in script
    assert 'text:"Attention required",tone:"bad"' in script
    assert '`Active ${activeText}${mode?` · ${mode}`:""}`' in script


def test_intentionally_uncommissioned_thermal_control_is_amber_not_fault_red():
    script = text()

    assert 'document.getElementById("fanThermalReadiness")' in script
    assert 'normalized.includes("thermal policy is not configured for automatic control")' in script
    assert 'const desired="Not commissioned · Observe only"' in script
    assert 'const desiredClass="value warn"' in script
    assert 'data-cockpit-readiness","uncommissioned"' in script


def test_mutation_observer_writes_are_idempotent():
    script = text()

    assert 'if(readiness.className!==desiredClass)' in script
    assert 'if(readiness.textContent!==desired)' in script
    assert 'if(stateNode.className!==desiredClass)' in script
    assert 'if(stateNode.textContent!==desiredText)' in script
    assert 'if(state.className!==desiredClass)' in script
    assert 'if(state.textContent!==desiredText)' in script

    assert 'readiness.classList.remove("bad","good")' not in script
    assert 'readiness.classList.add("value","warn")' not in script


def test_bottom_maintenance_cards_are_secondary_drawer():
    script = text()

    assert 'details.id="cockpitMaintenance"' in script
    assert '"Configuration & Mission Control"' in script
    assert 'document.getElementById("nightEnabled")?.closest("article")' in script
    assert 'document.getElementById("configMode")?.closest("article")' in script
    assert 'Direct hardware access' in script
    assert 'cockpit-maintenance-state' in script


def test_lcd_first_becomes_final_non_preview_baseline():
    script = text()

    assert "function promoteLcdFirstBaseline()" in script
    assert 'params.get("cockpit-preview")==="1"||params.has("layout")' in script
    assert 'const overview=document.getElementById("cockpitOverview")' in script
    assert 'const vfp=document.querySelector(".lcd-panel")' in script
    assert "grid.prepend(vfp)" in script
    assert "grid.insertBefore(overview,vfp.nextSibling)" in script
    assert 'document.body.dataset.cockpitBaseline="lcd-first"' in script
    assert 'document.body.classList.add("cockpit-final-lcd-first")' in script
    assert 'window.requestAnimationFrame(()=>{' in script
    assert 'window.requestAnimationFrame(promote)' in script
    assert '.cockpit-final-lcd-first #cockpitOverview{margin-top:-.28rem}' in script


def test_preview_layout_selector_remains_authoritative_during_comparison():
    script = text()

    start = script.index("function promoteLcdFirstBaseline(){")
    end = script.index("function cleanFooter(){", start)
    final_layout = script[start:end]

    assert 'if(params.get("cockpit-preview")==="1"||params.has("layout")) return;' in final_layout
