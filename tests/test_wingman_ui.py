from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _ui_source() -> str:
    return (
        ROOT / "truepanel/web/static/wingman.js"
    ).read_text(encoding="utf-8")


def _server_source() -> str:
    return (
        ROOT / "truepanel/web/pathfinder_server.py"
    ).read_text(encoding="utf-8")


def test_wingman_ui_is_explicit_operator_trigger_only():
    source = _ui_source()

    assert 'const BRIEF_URL="/api/v1/wingman/brief";' in source
    assert 'button.addEventListener("click",async()=>{' in source
    assert 'method:"POST"' in source

    assert 'truepanel:status' not in source
    assert "setInterval(" not in source

    assert "BRIEF ME" in source
    assert "Operator triggered · no automatic inference" in source


def test_wingman_ui_preserves_advisory_only_authority():
    source = _ui_source()

    assert "ADVISORY ONLY · CONTROL AUTHORITY FALSE" in source
    assert "payload.control_authority!==false" in source
    assert "payload.production_mutation!==false" in source
    assert "payload.advisory_only!==true" in source
    assert "Mission Control telemetry remains authoritative." in source


def test_wingman_ui_surfaces_grounding_sources():
    source = _ui_source()

    assert "Mission Control Reliability" in source
    assert "summary_source_ids" in source
    assert "item.source_ids" in source
    assert "sourceBadges" in source


def test_pathfinder_serves_and_injects_wingman_ui():
    source = _server_source()

    assert '_WINGMAN_SCRIPT = "wingman.js"' in source
    assert 'b"<!-- truepanel-wingman -->"' in source
    assert 'b\'\\n<script src="/wingman.js" defer></script>\\n\'' in source
    assert 'if parsed.path == f"/{_WINGMAN_SCRIPT}":' in source
    assert "if _WINGMAN_MARKER not in body:" in source
