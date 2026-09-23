"""Offline HoloDeck-style tests for the structured HOLD mapping boundary."""

from __future__ import annotations

import copy

import pytest

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
    with pytest.raises(ValueError, match="readiness unknown"):
        holds_from_trusted_snapshot(snapshot)
    # Missing readiness must not be translated into permission to explain.


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
    with pytest.raises(ValueError, match="not resolved"):
        holds_from_trusted_snapshot(snapshot)



@pytest.mark.parametrize("missing", ["reliability", "operator_guidance"])
def test_missing_authoritative_status_fails_closed(missing):
    snapshot = _snapshot()
    snapshot.pop(missing)
    with pytest.raises(ValueError, match="unavailable"):
        holds_from_trusted_snapshot(snapshot)


@pytest.mark.parametrize("value", [None, "UNKNOWN", "REVIEW", "INVALID"])
def test_unresolved_aegis_state_fails_closed(value):
    snapshot = _snapshot()
    snapshot["reliability"]["airworthiness"]["status"] = value
    with pytest.raises(ValueError, match="not resolved"):
        holds_from_trusted_snapshot(snapshot)



def _verified_snapshot():
    """One synthetic SMART card with independently corroborated Lifeline proof."""
    snapshot = _snapshot()
    evidence = snapshot["operator_guidance"][0]["runtime"]["evidence"]
    evidence.update({
        "pool": "HDDs", "vdev": "raidz1-0",
        "bay": 3, "device": "/dev/sdc", "serial_last4": "A123",
        "member_id": "12345",
    })
    original = dict(evidence)
    identity = {
        "mode": "wwn",
        "source": "udev_wwn_cross_checked_inventory",
        "confidence": "very_high",
        "stable_key": "wwn:synthetic",
        "device": "/dev/sdc",
        "bay": 3,
        "serial_last4": "A123",
    }
    repair = {
        "target": dict(evidence),
        "gates": [{"code": "physical_identity", "satisfied": True}],
    }
    snapshot["lifeline"] = {
        "sessions": [{
            "status": "active",
            "trigger_code": "storage.smart_warning",
            "original_fault": original,
            "drive_identity": identity,
            "last_session": repair,
        }],
    }
    return snapshot


def _storage_hold(snapshot):
    return next(hold for hold in holds_from_trusted_snapshot(snapshot)
                if hold.kind in {
                    HoldKind.PHYSICAL_SERVICE,
                    HoldKind.PHYSICAL_SERVICE_UNLOCALIZED,
                })


def test_independently_verified_current_identity_localizes_hold():
    snapshot = _verified_snapshot()
    hold = _storage_hold(snapshot)
    assert hold.kind is HoldKind.PHYSICAL_SERVICE
    assert hold.bay == 3
    view = project_operator_view(
        _model(), trusted_holds=holds_from_trusted_snapshot(snapshot)
    )
    assert "Bay 3: physical service HOLD" in str(view)
    assert view["generated_explanation"] is None
    assert view["hold_release_authorized"] is False


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s.pop("lifeline"),
        lambda s: s["lifeline"].update(sessions=[]),
        lambda s: s["lifeline"]["sessions"][0]["drive_identity"].update(
            mode="zfs_member", source="zfs_stable_member"
        ),
        lambda s: s["lifeline"]["sessions"][0]["drive_identity"].update(
            confidence="low"
        ),
        lambda s: s["lifeline"]["sessions"][0]["drive_identity"].update(
            bay=6
        ),
        lambda s: s["lifeline"]["sessions"][0]["drive_identity"].update(
            device="/dev/sdz"
        ),
        lambda s: s["lifeline"]["sessions"][0]["drive_identity"].update(
            serial_last4="B999"
        ),
        lambda s: s["lifeline"]["sessions"][0]["original_fault"].update(
            bay=6
        ),
        lambda s: s["lifeline"]["sessions"][0]["original_fault"].update(
            member_id="99999"
        ),
        lambda s: s["lifeline"]["sessions"][0]["last_session"]["target"].update(
            pool="not-HDDs"
        ),
        lambda s: s["lifeline"]["sessions"][0]["last_session"]["gates"][0].update(
            satisfied=False
        ),
        lambda s: s["lifeline"]["sessions"][0]["last_session"].update(
            gates=None
        ),
        lambda s: s["lifeline"]["sessions"][0].update(status="completed"),
        lambda s: s["lifeline"]["sessions"][0].update(
            trigger_code="storage.disk_faulted"
        ),
        lambda s: s["operator_guidance"][0]["runtime"]["evidence"].update(
            serial_last4=""
        ),
    ],
)
def test_unverified_conflicting_or_missing_proof_never_names_bay(mutate):
    snapshot = _verified_snapshot()
    mutate(snapshot)
    hold = _storage_hold(snapshot)
    assert hold.kind is HoldKind.PHYSICAL_SERVICE_UNLOCALIZED
    assert hold.bay is None
    view = project_operator_view(
        _model(), trusted_holds=holds_from_trusted_snapshot(snapshot)
    )
    assert "Bay 3" not in str(view)
    assert "Bay 6" not in str(view)
    assert view["generated_explanation"] is None


def test_ambiguous_duplicate_proof_never_names_bay():
    snapshot = _verified_snapshot()
    snapshot["lifeline"]["sessions"].append(
        copy.deepcopy(snapshot["lifeline"]["sessions"][0])
    )
    assert _storage_hold(snapshot).kind is HoldKind.PHYSICAL_SERVICE_UNLOCALIZED


def test_multiple_smart_incidents_do_not_collapse_into_a_single_bay():
    snapshot = _verified_snapshot()
    second = copy.deepcopy(snapshot["operator_guidance"][0])
    second["runtime"]["evidence"]["bay"] = 6
    second["runtime"]["evidence"]["device"] = "/dev/sdz"
    snapshot["operator_guidance"].append(second)
    assert _storage_hold(snapshot).kind is HoldKind.PHYSICAL_SERVICE_UNLOCALIZED


def test_no_hold_can_be_released_by_a_model_claim():
    snapshot = _verified_snapshot()
    snapshot["operator_guidance"][0]["runtime"]["action_gate"][
        "physical_service_ready"
    ] = True
    holds = holds_from_trusted_snapshot(snapshot)
    assert not any(hold.kind in {
        HoldKind.PHYSICAL_SERVICE,
        HoldKind.PHYSICAL_SERVICE_UNLOCALIZED,
    } for hold in holds)
    view = project_operator_view(_model(), trusted_holds=holds)
    assert view["hold_release_authorized"] is False
