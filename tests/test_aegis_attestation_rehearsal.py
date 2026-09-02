import json
from pathlib import Path

from truepanel.holodeck.aegis_attestations import (
    run_recovery_attestation_rehearsal,
)

ROOT = Path(__file__).resolve().parents[1]


def test_holodeck_ground_truth_rehearsal_fails_every_unsafe_path_closed():
    result = run_recovery_attestation_rehearsal()

    assert result["scenario"] == "aegis-recovery-ground-truth-v1"
    assert result["hardware_isolated"] is True
    assert result["field_validated"] is False
    assert result["control_authority"] is False
    assert result["measurements"] == {
        "cases": 7,
        "positive_ready": 1,
        "negative_holds": 6,
        "unsafe_false_ready": 0,
        "positive_attestations_accepted": 2,
    }
    assert result["cases"][0]["status"] == "EVIDENCE_READY"
    assert all(item["status"] == "HOLD" for item in result["cases"][1:])
    assert all(item["control_authority"] is False for item in result["cases"])


def test_rehearsal_preserves_specific_failure_modes_as_reusable_evidence():
    cases = {
        item["name"]: item for item in run_recovery_attestation_rehearsal()["cases"]
    }

    assert "attestation digest mismatch" in cases["mutated-statement"][
        "rejection_reasons"
    ]
    assert "attestation has expired" in cases["expired-evidence"][
        "rejection_reasons"
    ]
    assert "candidate identity is not strongly distinct" in cases[
        "reused-drive-identity"
    ]["rejection_reasons"]
    assert "provider mode is not governed" in cases["ungoverned-provider"][
        "rejection_reasons"
    ]
    assert cases["missing-backup"]["missing_kinds"] == [
        "backup.restore-verification"
    ]
    assert cases["ambiguous-duplicate"]["contradictions"]


def test_preserved_ground_truth_evidence_replays_exactly():
    expected = json.loads(
        (ROOT / "docs/evidence/aegis-recovery-ground-truth-v1.json").read_text()
    )

    assert run_recovery_attestation_rehearsal() == expected
