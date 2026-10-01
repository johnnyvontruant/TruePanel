"""Contracts for content-bound AEGIS operator action packets."""

import json
from pathlib import Path

from truepanel.holodeck.aegis_operator_action_packet import (
    run_operator_action_packet_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def test_operator_action_packet_is_public_bound_and_non_authorizing():
    evidence = run_operator_action_packet_checkride()

    assert evidence["status_counts"] == {
        "OPERATOR_ACTION_PACKET_VERIFIED": 1,
        "HOLD": 7,
        "DENIED": 2,
    }
    assert evidence["measurements"]["packets_verified"] == 1
    assert evidence["measurements"]["card_names_independent_boundary"] == 1
    assert evidence["measurements"]["action_satisfactions"] == 0
    assert evidence["measurements"]["independent_channels_manufactured"] == 0
    assert evidence["measurements"]["private_keys_accepted_by_truepanel"] == 0
    assert evidence["measurements"]["signer_invocations_by_truepanel"] == 0
    assert evidence["measurements"]["production_acceptances"] == 0
    assert evidence["measurements"]["deployments"] == 0
    assert evidence["measurements"]["hardware_actions"] == 0
    assert evidence["measurements"]["runtime_writes"] == 0
    assert evidence["recovery_coverage"] == {"total": 8, "trusted": 8, "gaps": 0}


def test_preserved_operator_action_packet_evidence_replays_exactly():
    preserved = json.loads(
        (ROOT / "docs/evidence/aegis-operator-action-packet-v1.json").read_text()
    )

    assert preserved == run_operator_action_packet_checkride()


def test_mission_control_names_packet_boundary_on_mobile():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()

    assert "Operator action packet · exact next gate + verifier + completed-stage digests" in source
    assert "Public explanation only · never satisfies the action or proves independent delivery" in source
