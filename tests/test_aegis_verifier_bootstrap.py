import json
from pathlib import Path

import pytest

from truepanel.aegis import verifier_bootstrap
from truepanel.aegis.verifier_bootstrap import verify_verifier_release
from truepanel.holodeck import aegis_independent_kit_auditor
from truepanel.holodeck.aegis_verifier_bootstrap import (
    run_verifier_bootstrap_checkride,
)


def _paths() -> tuple[Path, Path]:
    receipt = Path(verifier_bootstrap.__file__).with_name(
        "independent_verifier_release.json"
    ).resolve()
    source = Path(aegis_independent_kit_auditor.__file__).resolve()
    return receipt, source


def test_packaged_verifier_release_matches_exact_standalone_source():
    receipt, source = _paths()
    result = verify_verifier_release(receipt_path=receipt, source_path=source)

    assert result["status"] == "VERIFIER_CONTENT_PIN_VERIFIED"
    assert result["independent_channel_verified"] is False
    assert result["next_gate"] == "OPERATOR_OBTAINS_PIN_THROUGH_INDEPENDENT_CHANNEL"
    assert result["source_commit"] == "6bbda7b85142451562eb420f612478b311e6e8eb"
    assert result["production_authority"] is False
    assert result["deployment_authority"] is False
    assert result["hardware_authority"] is False


def test_verifier_release_rejects_relative_paths():
    with pytest.raises(ValueError, match="VerifierBootstrapUnsafePath"):
        verify_verifier_release(
            receipt_path="truepanel/aegis/independent_verifier_release.json",
            source_path="truepanel/holodeck/aegis_independent_kit_auditor.py",
        )


def test_verifier_bootstrap_checkride_fails_closed():
    result = run_verifier_bootstrap_checkride()

    assert result["status_counts"] == {
        "VERIFIER_CONTENT_PIN_VERIFIED": 1,
        "HOLD": 14,
    }
    assert result["measurements"]["unsafe_ready"] == 0
    assert result["measurements"]["independent_channels_manufactured"] == 0
    assert result["measurements"]["verifier_executions_during_pin_check"] == 0
    assert result["measurements"]["private_keys_accepted_by_truepanel"] == 0
    assert result["measurements"]["production_acceptances"] == 0
    assert result["recovery_coverage"] == {"total": 8, "trusted": 8, "gaps": 0}
    assert result["control_authority"] is False


def test_preserved_verifier_bootstrap_evidence_replays_exactly():
    evidence = Path("docs/evidence/aegis-verifier-bootstrap-v1.json")
    expected = json.loads(evidence.read_text())

    assert run_verifier_bootstrap_checkride() == expected
