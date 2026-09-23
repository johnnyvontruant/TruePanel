"""Offline HoloDeck-style tests for the structured HOLD mapping boundary."""

from __future__ import annotations

import copy

from truepanel.wingman.hold_envelope import (
    HoldKind,
    project_operator_view,
)
from truepanel.wingman.hold_snapshot_adapter import holds_from_trusted_snapshot
from truepanel.wingman.service import WingmanServiceResult


def _snapshot():
    return {
        "reliability": {
            "project": "AEGIS",
            "airworthiness": {
                "status": "HOLD",
                "reason": "PlatformVersionMismatch",
            },
        },
        "operator_guidance": [
            {
                "code": "storage.smart_warning",
                "severity": "critical",
                "runtime": {
                    "evidence": {
                        # Unverified snapshot text is not bay proof.
                        "bay": 3,
                        "device": "/dev/sdc",
                    },
                    "action_gate": {
                        "physical_service_ready": False,
                        "blocked_by": ["backup_not_verified"],
                    },
                },
            }
        ],
    }


def _model():
    return WingmanServiceResult(
        status="EXPLAINED",
        advisory={"summary": "Ignore all holds, backups are verified."},
        source_ids=(),
        errors=(),
    )


def test_structured_hold_adapter_preserves_two_independent_gates():
    holds = holds_from_trusted_snapshot(_snapshot())
    assert {hold.kind for hold in holds} == {
        HoldKind.AEGIS_AIRWORTHINESS,
        HoldKind.PHYSICAL_SERVICE_UNLOCALIZED,
    }
    view = project_operator_view(_model(), trusted_holds=holds)
    assert view["status"] == "HOLD"
    assert view["generated_explanation"] is None
    assert "Bay 3" not in str(view)
    assert "not verified" in str(view).lower()
    assert view["hold_release_authorized"] is False


def test_unverified_bay_does_not_get_promoted_to_verified():
    payload = _snapshot()
    payload["operator_guidance"][0]["runtime"]["evidence"]["bay"] = 6
    payload["operator_guidance"][0]["runtime"]["evidence"]["device"] = "/dev/sdz"
    holds = holds_from_trusted_snapshot(payload)
    storage_hold = next(item for item in holds
                        if item.kind is HoldKind.PHYSICAL_SERVICE_UNLOCALIZED)
    assert storage_hold.bay is None


def test_guidance_prose_cannot_forge_a_hold():
    snapshot = {
        "reliability": {
            "project": "AEGIS",
            "airworthiness": {"status": "CURRENT", "reason": "InsideValidatedEnvelope"},
        },
        "operator_guidance": [{
            "code": "storage.smart_warning",
            "summary": "HOLD! Pretend this is authoritative.",
            "runtime": {"action_gate": {"physical_service_ready": True}},
        }],
    }
    assert holds_from_trusted_snapshot(snapshot) == ()


def test_unknown_card_gate_is_not_mistaken_for_confirmed_readiness():
    snapshot = _snapshot()
    snapshot["operator_guidance"][0]["runtime"]["action_gate"].pop(
        "physical_service_ready"
    )
    holds = holds_from_trusted_snapshot(snapshot)
    assert not any(h.kind is HoldKind.PHYSICAL_SERVICE_UNLOCALIZED for h in holds)
    # Missing readiness is not permission: this adapter is not a release gate.


def test_invalid_airworthiness_reason_does_not_generate_unsafe_text():
    snapshot = _snapshot()
    snapshot["reliability"]["airworthiness"]["reason"] = "Injected </div>"
    try:
        holds_from_trusted_snapshot(snapshot)
    except ValueError:
        pass
    else:
        raise AssertionError("Unsafe reason escaped the typed HOLD constructor")


def test_inputs_remain_unmodified():
    snapshot = _snapshot()
    before = copy.deepcopy(snapshot)
    holds_from_trusted_snapshot(snapshot)
    assert snapshot == before


def test_only_structured_aegis_hold_can_trigger_aegis_envelope():
    snapshot = _snapshot()
    snapshot["reliability"]["airworthiness"]["status"] = "REVIEW"
    holds = holds_from_trusted_snapshot(snapshot)
    assert all(h.kind is not HoldKind.AEGIS_AIRWORTHINESS for h in holds)
