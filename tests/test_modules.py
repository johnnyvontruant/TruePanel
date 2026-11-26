from __future__ import annotations

import json

import pytest

from truepanel.modules import (
    CATALOG,
    CORE,
    DEVELOPER,
    LEGACY_INSTALLED,
    MODULES,
    PRESETS,
    dependents_of,
    is_module_enabled,
    resolve,
    selection_for_preset,
    selection_from_config,
    validate_catalog,
)
from truepanel.modules.commands import handle_module_command

core_ids = {m.id for m in CATALOG if m.tier == CORE}


def test_catalog_is_valid():
    assert validate_catalog() == []


def test_agreed_core_list():
    assert core_ids == {
        "flight_deck",
        "mission_control",
        "health",
        "history",
        "flight_recorder",
        "lifecycle",
    }


def test_every_module_has_operator_facing_text():
    for module in CATALOG:
        assert module.summary.strip()
        assert module.description.strip()
        assert module.version.count(".") == 2
        assert module.removable == (module.tier != CORE)


def test_missing_section_is_legacy_and_keeps_everything():
    for config in (None, {}, {"modules": None}, {"modules": {"preset": "x"}}):
        selection = selection_from_config(config)
        assert selection.legacy is True
        assert selection.installed == frozenset(LEGACY_INSTALLED)
        assert selection.installed == frozenset(MODULES)


def test_empty_installed_list_means_core_only():
    selection = selection_from_config({"modules": {"installed": []}})
    assert selection.legacy is False
    assert selection.installed == core_ids


def test_core_is_always_installed():
    selection = resolve(["vpn_status"])
    assert core_ids <= selection.installed
    assert "flight_deck" not in selection.auto_added


def test_requirements_are_added_with_a_reason():
    selection = selection_from_config({"modules": {"installed": ["loadmaster"]}})
    assert {"loadmaster", "cargo_bay"} <= selection.installed
    assert selection.auto_added == {"cargo_bay": "needed by Loadmaster"}


def test_explicit_choice_is_not_reported_as_auto_added():
    selection = resolve(["loadmaster", "cargo_bay"])
    assert "cargo_bay" not in selection.auto_added


def test_unknown_ids_are_reported_not_fatal():
    selection = resolve(["bogus", "vpn_status", "bogus", ""])
    assert selection.unknown == ("bogus",)
    assert "vpn_status" in selection.installed


def test_string_installed_value_is_accepted():
    selection = selection_from_config({"modules": {"installed": "vpn_status"}})
    assert "vpn_status" in selection.installed


def test_presets_nest_and_exclude_developer_tools():
    essentials = selection_for_preset("essentials").installed
    recommended = selection_for_preset("recommended").installed
    everything = selection_for_preset("everything").installed
    assert essentials == core_ids
    assert essentials < recommended < everything
    assert not any(MODULES[m].tier == DEVELOPER for m in everything)
    for name in PRESETS:
        selection = selection_for_preset(name)
        assert selection.auto_added == {}, name


def test_unknown_preset_raises():
    with pytest.raises(KeyError):
        selection_for_preset("kitchen-sink")


def test_to_config_round_trips_and_omits_core():
    selection = resolve(["loadmaster", "reliability"])
    section = selection.to_config()
    assert not set(section["installed"]) & core_ids
    again = selection_from_config({"modules": section})
    assert again.installed == selection.installed


def test_dependents_block_removal():
    installed = resolve(["loadmaster", "reliability"]).installed
    assert dependents_of("cargo_bay", installed) == ("loadmaster",)
    assert dependents_of("oracle", installed) == ("reliability",)
    assert dependents_of("vpn_status", installed) == ()


def test_is_module_enabled_rejects_typos():
    assert is_module_enabled({}, "loadmaster") is True
    with pytest.raises(KeyError):
        is_module_enabled({}, "load_master")


class Args:
    def __init__(self, action, **values):
        self.modules_action = action
        self.modules_config = values.pop("config")
        self.modules_json = values.pop("json", False)
        self.modules_developer = values.pop("developer", False)
        for key, value in values.items():
            setattr(self, key, value)


def test_cli_list_json(tmp_path, capsys):
    config = tmp_path / "truepanel.yaml"
    config.write_text("modules:\n  installed: [loadmaster]\n")
    assert handle_module_command(Args("list", config=str(config), json=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    status = {m["id"]: m["status"] for m in payload["modules"]}
    assert payload["legacy"] is False
    assert status["flight_deck"] == "core"
    assert status["loadmaster"] == "installed"
    assert status["cargo_bay"] == "installed"
    assert status["vpn_status"] == "available"


def test_cli_show_unknown_module(tmp_path, capsys):
    args = Args("show", config=str(tmp_path / "none.yaml"), module_id="nope")
    assert handle_module_command(args) == 2


def test_cli_validate(capsys):
    assert handle_module_command(Args("validate", config="unused")) == 0
    assert "OK" in capsys.readouterr().out
