import json
from importlib.resources import files
from pathlib import Path

from truepanel.hangar import (
    HANGAR_STATES,
    load_registry,
    render_status_views,
    validate_registry,
)
from truepanel.hangar.registry import status_summary

ROOT = Path(__file__).resolve().parents[1]


def test_hangar_registry_is_packaged_valid_and_uses_exact_states():
    packaged = files("truepanel.hangar").joinpath("registry.json")
    registry = json.loads(packaged.read_text(encoding="utf-8"))

    assert registry["states"] == list(HANGAR_STATES)
    assert validate_registry(registry, root=ROOT) == ()
    assert status_summary(registry) == {
        "FUTURE": 2,
        "IN_PROGRESS": 0,
        "COMPLETED": 10,
        "FAILED": 2,
    }


def test_hangar_views_are_generated_and_do_not_move_dossiers(tmp_path):
    registry = load_registry()
    rendered = render_status_views(tmp_path, registry)

    assert tuple(rendered) == HANGAR_STATES
    for state, generated in rendered.items():
        assert generated.read_text() == (ROOT / "docs" / "hangar" / f"{state.lower()}.md").read_text()
        assert "Generated from `truepanel/hangar/registry.json`" in generated.read_text()


def test_hangar_state_contracts_fail_closed():
    registry = load_registry()
    failed = next(item for item in registry["experiments"] if item["state"] == "FAILED")
    failed["outcome"].pop("reusable_lesson")
    future = next(item for item in registry["experiments"] if item["state"] == "FUTURE")
    future["hypothesis"] = ""

    errors = validate_registry(registry)

    assert any("failed experiment needs reusable_lesson" in error for error in errors)
    assert any("hypothesis must be non-empty" in error for error in errors)
