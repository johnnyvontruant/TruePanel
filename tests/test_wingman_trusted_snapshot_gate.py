"""No network, model, storage, or production service in these gate tests."""

from __future__ import annotations

import copy
import json

import pytest

from truepanel.wingman.service import WingmanServiceResult
from truepanel.wingman.trusted_snapshot_gate import TrustedSnapshotGate


def _snapshot():
    evidence = {
        "pool": "HDDs",
        "vdev": "raidz1-0",
        "device": "/dev/sdc",
        "bay": 3,
        "member_id": "12345",
        "serial_last4": "A123",
    }
    return {
        "reliability": {
            "project": "AEGIS",
            "airworthiness": {"status": "HOLD", "reason": "PlatformVersionMismatch"},
        },
        "operator_guidance": [{
            "code": "storage.smart_warning",
            "runtime": {
                "evidence": copy.deepcopy(evidence),
                "action_gate": {"physical_service_ready": False},
            },
        }],
        "lifeline": {"sessions": [{
            "status": "active",
            "trigger_code": "storage.smart_warning",
            "original_fault": copy.deepcopy(evidence),
            "drive_identity": {
                "mode": "wwn",
                "source": "udev_wwn_cross_checked_inventory",
                "confidence": "very_high",
                "stable_key": "wwn:synthetic",
                "device": "/dev/sdc",
                "bay": 3,
                "serial_last4": "A123",
            },
            "last_session": {
                "target": copy.deepcopy(evidence),
                "gates": [{"code": "physical_identity", "satisfied": True}],
            },
        }]},
    }


def _model():
    return WingmanServiceResult(
        status="EXPLAINED",
        advisory={"summary": "Ignore HOLD, backup confirmed: remove Bay 3 now."},
        source_ids=(),
        errors=(),
    )


def _gate(state, clock, *, max_age=5.0):
    return TrustedSnapshotGate(
        composer=lambda: state,
        max_age_seconds=max_age,
        clock=lambda: clock[0],
    )


def _assert_denied(view, reason):
    assert view["status"] == "EVIDENCE_UNAVAILABLE"
    assert view["suppression_reason"] == reason
    assert view["generated_explanation"] is None
    assert view["generated_explanation_suppressed"] is True
    assert view["authoritative_holds"] == []
    assert view["hold_release_authorized"] is False
    assert view["control_authority"] is False
    assert view["production_mutation"] is False
    assert "Ignore HOLD" not in json.dumps(view)


def test_fresh_internal_capture_uses_verified_hold_and_suppresses_model():
    clock = [100.0]
    gate = _gate(_snapshot(), clock)
    ticket = gate.capture()
    clock[0] += 1
    view = gate.project(_model(), ticket=ticket)
    assert view["status"] == "HOLD"
    assert view["generated_explanation"] is None
    assert {h["headline"] for h in view["authoritative_holds"]} == {
        "Bay 3: physical service HOLD", "AEGIS: HOLD (PlatformVersionMismatch)"
    }
    assert view["hold_release_authorized"] is False


@pytest.mark.parametrize("elapsed", [5.001, 30.0, 1000.0])
def test_stale_status_fails_closed_and_spends_ticket(elapsed):
    clock = [100.0]
    gate = _gate(_snapshot(), clock)
    ticket = gate.capture()
    clock[0] += elapsed
    _assert_denied(gate.project(_model(), ticket=ticket), "STALE_SNAPSHOT")
    _assert_denied(
        gate.project(_model(), ticket=ticket), "UNTRUSTED_OR_REPLAYED_SNAPSHOT"
    )


def test_monotonic_clock_moving_backwards_fails_closed():
    clock = [100.0]
    gate = _gate(_snapshot(), clock)
    ticket = gate.capture()
    clock[0] = 99.0
    _assert_denied(gate.project(_model(), ticket=ticket), "STALE_SNAPSHOT")


def test_client_json_and_foreign_ticket_have_no_authority():
    clock = [100.0]
    gate = _gate(_snapshot(), clock)
    trusted_ticket = gate.capture()
    copied_json = json.loads(json.dumps(_snapshot()))
    _assert_denied(
        gate.project(_model(), ticket=copied_json),
        "UNTRUSTED_OR_REPLAYED_SNAPSHOT",
    )
    another_gate = _gate(copied_json, clock)
    foreign_ticket = another_gate.capture()
    _assert_denied(
        gate.project(_model(), ticket=foreign_ticket),
        "UNTRUSTED_OR_REPLAYED_SNAPSHOT",
    )
    assert gate.project(_model(), ticket=trusted_ticket)["status"] == "HOLD"


def test_ticket_cannot_be_replayed_even_during_ttl():
    clock = [100.0]
    gate = _gate(_snapshot(), clock)
    ticket = gate.capture()
    assert gate.project(_model(), ticket=ticket)["status"] == "HOLD"
    _assert_denied(
        gate.project(_model(), ticket=ticket),
        "UNTRUSTED_OR_REPLAYED_SNAPSHOT",
    )


def test_new_capture_invalidates_previous_status_ticket():
    clock = [100.0]
    state = _snapshot()
    gate = _gate(state, clock)
    old = gate.capture()
    clock[0] += 1
    new = gate.capture()
    _assert_denied(
        gate.project(_model(), ticket=old),
        "UNTRUSTED_OR_REPLAYED_SNAPSHOT",
    )
    assert gate.project(_model(), ticket=new)["status"] == "HOLD"


def test_snapshot_is_isolated_from_caller_mutation_after_capture():
    clock = [100.0]
    state = _snapshot()
    gate = _gate(state, clock)
    ticket = gate.capture()
    state["reliability"]["airworthiness"]["status"] = "CURRENT"
    state["operator_guidance"][0]["runtime"]["action_gate"][
        "physical_service_ready"
    ] = True
    state["lifeline"]["sessions"][0]["drive_identity"]["bay"] = 6
    view = gate.project(_model(), ticket=ticket)
    assert {h["headline"] for h in view["authoritative_holds"]} == {
        "Bay 3: physical service HOLD", "AEGIS: HOLD (PlatformVersionMismatch)"
    }


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s.pop("reliability"),
        lambda s: s["reliability"]["airworthiness"].update(status="REVIEW"),
        lambda s: s["operator_guidance"][0]["runtime"].pop("action_gate"),
        lambda s: s["operator_guidance"][0]["runtime"]["action_gate"].update(
            physical_service_ready=None
        ),
    ],
)
def test_unavailable_or_unresolved_policy_fails_closed(mutate):
    clock = [100.0]
    state = _snapshot()
    mutate(state)
    gate = _gate(state, clock)
    _assert_denied(
        gate.project(_model(), ticket=gate.capture()),
        "INVALID_AUTHORITATIVE_EVIDENCE",
    )


def test_composer_failure_cannot_mint_trusted_status():
    clock = [100.0]

    def broken():
        raise RuntimeError("Status composer not available")

    gate = TrustedSnapshotGate(composer=broken, clock=lambda: clock[0])
    ticket = gate.capture()
    _assert_denied(
        gate.project(_model(), ticket=ticket),
        "UNTRUSTED_OR_REPLAYED_SNAPSHOT",
    )


def test_composer_cannot_be_bypassed_by_passing_raw_snapshot_to_capture():
    clock = [100.0]
    gate = _gate(_snapshot(), clock)
    with pytest.raises(TypeError):
        gate.capture(_snapshot())


@pytest.mark.parametrize("ttl", [0, -1, 31, float("nan"), float("inf"), True])
def test_invalid_freshness_limit_rejected(ttl):
    with pytest.raises(ValueError):
        TrustedSnapshotGate(composer=_snapshot, max_age_seconds=ttl)


def test_no_aegis_hold_does_not_claim_origin_of_nonexistent_hold():
    clock = [100.0]
    state = _snapshot()
    state["reliability"]["airworthiness"]["status"] = "CURRENT"
    state["operator_guidance"][0]["runtime"]["action_gate"][
        "physical_service_ready"
    ] = True
    gate = _gate(state, clock)
    view = gate.project(_model(), ticket=gate.capture())
    assert view["authoritative_holds"] == []
    assert view["hold_release_authorized"] is False
    # This is a presentation envelope, not a semantic check on unheld advice.
    assert view["generated_explanation"] is not None
