import json
from pathlib import Path

from truepanel.aegis import OPERATOR_HANDOFF_SCHEMA, OPERATOR_KEY_ID
from truepanel.aegis.operator_handoff import canonical_development_statement
from truepanel.holodeck.aegis_operator_handoff import run_operator_handoff_checkride
from truepanel.holodeck.aegis_single_operator_development import (
    development_fixture_materials,
)

ROOT = Path(__file__).resolve().parents[1]


def test_real_sshsig_handoff_holds_closed_and_denies_stronger_consumers():
    report = run_operator_handoff_checkride()
    assert report["status_counts"] == {
        "READY_FOR_OFFLINE_SIGNATURE": 1,
        "ELIGIBLE_FOR_DEVELOPMENT_CANDIDATE_REVIEW": 1,
        "HOLD": 10,
        "DENIED": 5,
    }
    assert report["measurements"] == {
        "offline_signing_ready": 1,
        "development_eligible": 1,
        "adversarial_holds": 10,
        "stronger_consumers_denied": 5,
        "false_eligible_paths": 0,
        "production_acceptances": 0,
        "deployments": 0,
        "hardware_actions": 0,
        "runtime_writes": 0,
    }
    assert report["fixture_private_keys_retained"] == 0
    assert report["production_keys"] == 0
    assert report["production_mutation"] is False
    assert report["control_authority"] is False


def test_statement_is_canonical_and_excludes_signature():
    receipt = development_fixture_materials()["receipt"]
    statement = json.loads(canonical_development_statement(receipt))
    assert "signature" not in statement
    assert statement["operator_id"] == "jt"
    assert statement["key_id"] == OPERATOR_KEY_ID
    assert statement["production_authority"] is False
    assert OPERATOR_HANDOFF_SCHEMA.endswith("/v1")


def test_preserved_operator_handoff_evidence_replays_exactly():
    archived = json.loads(
        (ROOT / "docs/evidence/aegis-operator-key-handoff-v1.json").read_text()
    )
    assert run_operator_handoff_checkride() == archived


def test_mission_control_exposes_key_and_signature_state_on_mobile():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Public key roster ·" in source
    assert "Operator signature ·" in source
    assert "Production authority · NO" in source
