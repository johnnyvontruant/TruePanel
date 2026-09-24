"""HoloDeck-style deterministic presentation tests; no model or NAS access."""

from __future__ import annotations

import copy

import pytest

from truepanel.guidance.catalog import guidance_codes, guidance_payload
from truepanel.guidance.plain_language import (
    plain_language_codes,
    plain_language_for_card,
)


def _card(code, *, ready=False):
    card = guidance_payload(code)
    card["runtime"] = {
        "evidence": {},
        "action_gate": {
            "physical_service_ready": ready,
            "destructive_actions_ready": False,
            "blocked_by": [] if ready else ["not_verified"],
        },
    }
    return card


def test_entire_real_guidance_catalogue_has_operator_text():
    assert plain_language_codes() == guidance_codes()
    for code in guidance_codes():
        text = plain_language_for_card(_card(code))
        assert text["code"] == code
        for field in (
            "headline",
            "what_happened",
            "why_it_matters",
            "what_to_do",
            "do_not",
            "when_it_is_resolved",
        ):
            assert isinstance(text[field], str) and len(text[field]) > 24
        assert text["runtime_model_required"] is False
        assert text["authorization_granted"] is False


@pytest.mark.parametrize(
    "code",
    ["storage.smart_warning", "storage.disk_faulted", "storage.pool_degraded"],
)
def test_storage_cards_do_not_grant_service_or_destructive_authority(code):
    text = plain_language_for_card(_card(code))
    assert text["physical_service_ready"] is False
    assert text["destructive_actions_ready"] is False
    assert text["authorization_granted"] is False
    assert "not ready" in text["do_not"].lower()
    assert "not authorized" in text["do_not"].lower()


def test_critical_smart_condition_is_not_softened_by_passed_or_online():
    card = _card("storage.smart_warning")
    card["severity"] = "critical"
    card["runtime"]["evidence"] = {
        "smart_health": "PASSED",
        "zfs_state": "ONLINE",
        "pending": 123,
        "bay": None,
    }
    text = plain_language_for_card(card)
    assert text["headline"] == "A drive has serious signs of failure"
    assert "PASSED" in text["why_it_matters"]
    assert "ONLINE" in text["why_it_matters"]
    assert "exact physical bay has not been established" in text["what_to_do"]
    assert "HOLD" in text["why_it_matters"]


def test_operator_readiness_never_becomes_catalogue_authorization():
    card = _card("storage.disk_faulted", ready=True)
    card["runtime"]["action_gate"]["destructive_actions_ready"] = True
    text = plain_language_for_card(card)
    assert text["physical_service_ready"] is True
    assert text["destructive_actions_ready"] is True
    assert text["authorization_granted"] is False
    assert "operator-approved" in text["what_to_do"]


def test_missing_or_malformed_gate_fails_closed():
    card = _card("storage.smart_warning", ready=True)
    card.pop("runtime")
    text = plain_language_for_card(card)
    assert text["physical_service_ready"] is False
    assert text["destructive_actions_ready"] is False


def test_input_is_not_mutated_and_response_is_independent():
    card = _card("network.link_down")
    original = copy.deepcopy(card)
    result = plain_language_for_card(card)
    result["headline"] = "Edited outside the catalogue"
    assert card == original
    assert plain_language_for_card(card)["headline"] != result["headline"]


@pytest.mark.parametrize("code", ["other.fake_fault", "", "AEGIS"])
def test_unknown_fault_has_no_fabricated_explanation(code):
    with pytest.raises(ValueError, match="No plain-language explanation"):
        plain_language_for_card({"code": code})
