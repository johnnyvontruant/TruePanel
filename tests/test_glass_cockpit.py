import json
from importlib.resources import files
from pathlib import Path

from truepanel.glass_cockpit import COHORT_COUNTS, benchmark, validate_corpus
from truepanel.hangar import load_registry
from truepanel.hangar.registry import status_summary

ROOT = Path(__file__).resolve().parents[1]


def test_exactly_100_traceable_interfaces_across_declared_cohorts():
    assert validate_corpus() == ()
    assert sum(COHORT_COUNTS.values()) == 100


def test_three_candidates_use_disclosed_structural_heuristics():
    result = benchmark()
    assert result["disclosure"] == (
        "Automated structural heuristics, not human usability results"
    )
    assert result["tasks"] == 8
    assert result["winner"] == "B"
    assert [item["id"] for item in result["candidates"]] == ["A", "B", "C"]
    assert all(len(item["task_taps"]) == 8 for item in result["candidates"])


def test_candidates_are_packaged_executable_and_phone_safe_by_contract():
    candidates = files("truepanel.glass_cockpit").joinpath("candidates")
    for name in ("a.html", "b.html", "c.html"):
        source = candidates.joinpath(name).read_text(encoding="utf-8")
        assert 'name="viewport"' in source
        assert "@media(max-width:760px)" in source
        assert 'data-task="1"' in source
        assert 'data-task="6"' in source
        assert "overflow-x" not in source


def test_production_candidate_reuses_shared_stream_and_has_no_polling():
    source = (ROOT / "truepanel/web/static/glass-cockpit.js").read_text()
    assert 'window.addEventListener("truepanel:status"' in source
    assert "setInterval" not in source
    assert "fetch(" not in source
    assert "SAFEST MOVE" in source
    assert "PROOF" in source
    assert "prefers-reduced-motion:reduce" in source
    assert "min-height:44px" in source
    assert 'role="img"' in source


def test_ambient_background_is_static_and_semantically_neutral():
    source = (ROOT / "truepanel/web/static/glass-cockpit.js").read_text()
    start = source.index("/* gc-ambient-start")
    end = source.index("/* gc-ambient-end */", start)
    ambient = source[start:end]

    assert "--gc-ambient-grid" in ambient
    assert "data:image/svg+xml" in ambient
    assert "stroke-opacity='.17'" in ambient
    assert "background-size:144px 83px" in ambient
    assert "background-attachment:fixed" in ambient
    assert "--gc-ambient-a:#e3e6ed" in ambient
    assert "--gc-ambient-b:#cfd4de" in ambient
    assert "animation:" not in ambient
    assert "fetch(" not in ambient

    for semantic_color in (
        "var(--good)",
        "var(--warn)",
        "var(--bad)",
        "var(--accent)",
        "var(--accent-soft)",
    ):
        assert semantic_color not in ambient


def test_liquid_glass_is_static_additive_and_semantically_neutral():
    source = (ROOT / "truepanel/web/static/glass-cockpit.js").read_text()
    start = source.index("/* gc-liquid-glass-start")
    end = source.index("/* gc-liquid-glass-end */", start)
    glass = source[start:end]

    assert "blur(32px)" in glass
    assert "saturate(132%)" in glass
    assert "contrast(103%)" in glass
    assert "--gc-glass-shadow" in glass
    assert "--gc-glass-wash:rgba(255,255,255,.065)" in glass
    assert "--gc-glass-wash:rgba(255,255,255,.012)" in glass
    assert ".card::after" in glass
    assert "pointer-events:none" in glass
    assert "linear-gradient(var(--gc-glass-wash),var(--gc-glass-wash))" in glass
    assert "radial-gradient(120% 86% at 0% 0%" in glass
    assert "0 12px 28px var(--gc-glass-shadow)" in glass
    assert "forced-colors:active" in glass
    assert "animation:" not in glass
    assert "fetch(" not in glass
    assert "transform:" not in glass

    for semantic_color in (
        "var(--good)",
        "var(--warn)",
        "var(--bad)",
        "var(--accent)",
        "var(--accent-soft)",
    ):
        assert semantic_color not in glass


def test_health_annunciators_reuse_live_health_node_in_persistent_header():
    source = (ROOT / "truepanel/web/static/glass-cockpit.js").read_text()
    start = source.index("function installHealthAnnunciatorNavigation()")
    end = source.index("function installRefractionExperiment()", start)
    nav = source[start:end]

    assert 'document.getElementById("healthSubsystems")' in nav
    assert 'document.querySelector(".health-command")' in nav
    assert 'document.querySelector(".topbar")' in nav
    assert 'topbar.insertBefore(subsystems,connection)' in nav
    assert 'subsystems.classList.add("gc-health-annunciators")' in nav
    assert 'subsystems.setAttribute("role","navigation")' in nav
    assert 'subsystems.setAttribute("aria-label","System health navigation")' in nav
    assert "healthCard.hidden=true" in nav
    assert "cloneNode" not in nav


def test_health_annunciators_map_all_six_domains_to_real_cockpit_targets():
    source = (ROOT / "truepanel/web/static/glass-cockpit.js").read_text()
    start = source.index("function healthTarget(label)")
    end = source.index("function installHealthAnnunciatorNavigation()", start)
    mapping = source[start:end]

    assert 'cooling:document.getElementById("fanActiveProfile")?.closest("article")' in mapping
    assert 'thermal:document.getElementById("fanThermalTemperature")?.closest("article")' in mapping
    assert 'storage:document.getElementById("pools")?.closest("article")' in mapping
    assert 'network:document.getElementById("network")?.closest("article")' in mapping
    assert '"front panel":document.querySelector(".lcd-panel")' in mapping
    assert 'services:document.getElementById("configMode")?.closest("article")' in mapping


def test_health_annunciators_are_keyboard_mobile_and_reduced_motion_safe():
    source = (ROOT / "truepanel/web/static/glass-cockpit.js").read_text()
    start = source.index("/* gc-health-nav-start")
    end = source.index("/* gc-health-nav-end */", start)
    styles = source[start:end]

    assert 'item.setAttribute("role","button")' in source
    assert "item.tabIndex=0" in source
    assert 'event.key!=="Enter"&&event.key!==" "' in source
    assert "event.preventDefault()" in source
    assert 'parent.tagName==="DETAILS"' in source
    assert "parent.open=true" in source
    assert 'window.matchMedia?.("(prefers-reduced-motion: reduce)")' in source
    assert 'target.scrollIntoView({behavior:reduced?"auto":"smooth",block:"center"})' in source
    assert "new MutationObserver(annotate).observe(subsystems" in source
    assert "overflow-x:auto" in styles
    assert "scrollbar-width:none" in styles
    assert "flex:1 0 100%" in styles
    assert "min-height:36px" in styles


def test_svg_refraction_v2_distorts_a_copied_substrate_and_falls_back_to_v1_glass():
    source = (ROOT / "truepanel/web/static/glass-cockpit.js").read_text()
    start = source.index("function installRefractionExperiment()")
    end = source.index("function install(){", start)
    refraction = source[start:end]
    style_start = source.index("/* gc-refraction-start")
    style_end = source.index("/* gc-refraction-end */", style_start)
    styles = source[style_start:style_end]

    assert 'params.get("refraction")!=="1"' in refraction
    assert 'document.getElementById("healthSubsystems")' in refraction
    assert 'window.CSS?.supports?.("filter",filterValue)' in refraction
    assert 'document.body.dataset.gcRefraction="fallback"' in refraction
    assert 'document.body.dataset.gcRefraction="substrate"' in refraction
    assert 'document.createElementNS(ns,"svg")' in refraction
    assert 'document.createElementNS(ns,"feTurbulence")' in refraction
    assert 'document.createElementNS(ns,"feGaussianBlur")' in refraction
    assert 'document.createElementNS(ns,"feDisplacementMap")' in refraction
    assert 'displacement.setAttribute("scale","14")' in refraction
    assert 'turbulence.setAttribute("baseFrequency","0.010 0.028")' in refraction
    assert 'turbulence.setAttribute("numOctaves","1")' in refraction
    assert 'pane.classList.add("gc-refraction-substrate")' in refraction
    assert '.gc-refraction-substrate .health-subsystem::before' in styles
    assert "background:var(--gc-ambient-grid)" in styles
    assert "background-attachment:fixed,fixed" in styles
    assert 'filter:url("#gcRefraction") contrast(108%) saturate(104%)' in styles
    assert "opacity:.52" in styles
    assert 'backdrop-filter:url("#gcRefraction")' not in styles
    assert "requestAnimationFrame" not in refraction
    assert "setInterval" not in refraction
    assert "fetch(" not in refraction
    assert "animation:" not in styles


def test_server_exposes_glass_cockpit_asset_in_full_stack():
    server = (ROOT / "truepanel/web/server.py").read_text()
    pathfinder = (ROOT / "truepanel/web/pathfinder_server.py").read_text()
    assert 'b"<!-- truepanel-glass-cockpit -->"' in server
    assert '"/glass-cockpit.js"' in server
    assert "_server._GLASS_COCKPIT_MARKER" in pathfinder


def test_hangar_closed_experiment_and_evidence_agree():
    registry = load_registry()
    experiment = next(item for item in registry["experiments"] if item["id"] == "TP-EXP-0014")
    evidence = json.loads((ROOT / experiment["evidence"][0]["path"]).read_text())
    assert experiment["state"] == "COMPLETED"
    assert evidence["winner"] == "B"
    assert evidence["corpus"]["total"] == 100
    assert status_summary(registry) == {
        "FUTURE": 2, "IN_PROGRESS": 0, "COMPLETED": 10, "FAILED": 2,
    }
