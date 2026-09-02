import json
from pathlib import Path

from truepanel.holodeck.aegis_credential_session import (
    run_credential_session_rehearsal,
)


def test_credential_session_rehearsal_is_fail_closed_and_secret_free():
    proof = run_credential_session_rehearsal()
    measurements = proof["measurements"]
    assert proof["hardware_isolated"] is True
    assert proof["field_validated"] is False
    assert proof["control_authority"] is False
    assert measurements == {
        "positive_runtime_status": "READY",
        "verified_tls": True,
        "persistent_connections": 1,
        "authentication_calls": 1,
        "passive_calls": 3,
        "unsafe_scenarios": 6,
        "unsafe_holds": 6,
        "credential_occurrences_in_evidence": 0,
        "mutating_method_calls": 0,
        "runtime_credential_writes": 0,
    }
    assert "HOLODECK-API-KEY" not in json.dumps(proof)


def test_preserved_credential_session_evidence_replays_exactly():
    expected = json.loads(
        Path("docs/evidence/aegis-credential-safe-session-v1.json").read_text()
    )
    assert run_credential_session_rehearsal() == expected
