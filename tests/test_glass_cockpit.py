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
        "FUTURE": 2, "IN_PROGRESS": 1, "COMPLETED": 15, "FAILED": 2,
    }
