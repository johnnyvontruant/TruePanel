from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from truepanel.aegis.coverage import coverage_matrix
from truepanel.aegis.rehearsal import rehearse_recovery_paths
from truepanel.aegis.reliability import AegisReliabilityEngine
from truepanel.aegis.ssh_verifier import OpenSshSignatureVerifier
from truepanel.aegis.temperature_authenticated_acceptance import (
    KEY_ID,
    NAMESPACE,
    build_temperature_acceptance_statement,
    evaluate_authenticated_temperature_acceptance,
)
from truepanel.aegis.temperature_coverage import (
    build_temperature_coverage_candidate,
    rehearse_temperature_coverage,
)
from truepanel.aegis.temperature_coverage_appraisal import (
    appraise_temperature_coverage,
    temperature_coverage_implementation_sha256,
)
from truepanel.aegis.temperature_development_acceptance import (
    CONFIRMATION_SCHEMA,
    OPERATOR_ID,
    REQUIRED_STATEMENT,
    SCOPE,
    prepare_temperature_development_acceptance,
)
from truepanel.holodeck.aegis_temperature_authenticated_acceptance import (
    run_temperature_authenticated_acceptance_checkride,
)
from truepanel.holodeck.aegis_temperature_blind_spot import (
    run_temperature_blind_spot_checkride,
)

ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-10-11T04:30:00Z"


def _materials():
    accepted = coverage_matrix(rehearse_recovery_paths())
    candidate = build_temperature_coverage_candidate(
        accepted, rehearse_temperature_coverage()
    )
    evidence = run_temperature_blind_spot_checkride()
    appraisal = appraise_temperature_coverage(
        accepted,
        candidate,
        evidence,
        implementation_sha256=temperature_coverage_implementation_sha256(
            run_temperature_blind_spot_checkride
        ),
    )
    request = prepare_temperature_development_acceptance(candidate, appraisal)
    confirmation = {
        "schema": CONFIRMATION_SCHEMA,
        "operator_id": OPERATOR_ID,
        "scope": SCOPE,
        "statement": REQUIRED_STATEMENT,
        "subjects": request["subjects"],
        "issued_at": "2026-10-11T04:00:00Z",
        "expires_at": "2026-10-12T04:00:00Z",
    }
    return candidate, appraisal, confirmation


def _verifier_and_signature(tmp_path: Path, statement: bytes):
    key = tmp_path / "jt-development"
    subprocess.run(
        ["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
        check=True,
    )
    message = tmp_path / "statement.json"
    message.write_bytes(statement)
    subprocess.run(
        [
            "/usr/bin/ssh-keygen",
            "-Y",
            "sign",
            "-f",
            str(key),
            "-n",
            NAMESPACE,
            str(message),
        ],
        check=True,
    )
    roster = tmp_path / "allowed_signers"
    roster.write_text(
        f"{KEY_ID} {key.with_suffix('.pub').read_text(encoding='ascii')}",
        encoding="ascii",
    )
    os.chmod(roster, 0o600)
    signature = Path(f"{message}.sig").read_text(encoding="ascii")
    verifier = OpenSshSignatureVerifier(
        roster, namespace=NAMESPACE, expected_key_ids=(KEY_ID,)
    )
    return verifier, signature


def test_missing_confirmation_and_signature_stop_at_distinct_action_gates():
    candidate, appraisal, confirmation = _materials()
    no_confirmation = evaluate_authenticated_temperature_acceptance(
        candidate, appraisal, None, None, None, now_utc=NOW
    )
    no_signature = evaluate_authenticated_temperature_acceptance(
        candidate, appraisal, confirmation, None, None, now_utc=NOW
    )
    assert no_confirmation["status"] == "ACTION_REQUIRED_OPERATOR_CONFIRMATION"
    assert no_signature["status"] == "ACTION_REQUIRED_OPERATOR_SIGNATURE"
    assert no_signature["operator_signature_verified"] is False
    assert no_signature["accepted"] is False
    assert no_signature["deployment_authority"] is False


def test_real_sshsig_authenticates_only_the_exact_development_statement(tmp_path):
    candidate, appraisal, confirmation = _materials()
    statement = build_temperature_acceptance_statement(
        candidate, appraisal, confirmation, now_utc=NOW
    )
    verifier, signature = _verifier_and_signature(tmp_path, statement)
    result = evaluate_authenticated_temperature_acceptance(
        candidate, appraisal, confirmation, signature, verifier, now_utc=NOW
    )
    assert result["status"] == "AUTHENTICATED_DEVELOPMENT_ACCEPTED_FOR_REVIEW"
    assert result["operator_signature_verified"] is True
    assert result["development_review_accepted"] is True
    for field in (
        "accepted",
        "installed",
        "runtime_authority",
        "production_authority",
        "deployment_authority",
        "hardware_authority",
        "storage_write_authority",
        "network_authority",
        "automatic_promotion",
    ):
        assert result[field] is False

    changed = dict(confirmation)
    changed["issued_at"] = "2026-10-11T04:01:00Z"
    replay = evaluate_authenticated_temperature_acceptance(
        candidate, appraisal, changed, signature, verifier, now_utc=NOW
    )
    assert replay["status"] == "HOLD"
    assert replay["operator_signature_verified"] is False

    unavailable = evaluate_authenticated_temperature_acceptance(
        candidate, appraisal, confirmation, signature, None, now_utc=NOW
    )
    assert unavailable["status"] == "HOLD"
    assert unavailable["operator_signature_verified"] is False


def test_checkride_uses_real_sshsig_and_retains_no_fixture_keys():
    report = run_temperature_authenticated_acceptance_checkride()
    assert report["measurements"] == {
        "scenario_count": 11,
        "operator_confirmation_required_count": 1,
        "operator_signature_required_count": 1,
        "authenticated_development_acceptance_count": 1,
        "hold_count": 8,
        "fixture_private_keys_created": 2,
        "fixture_private_keys_retained": 0,
        "production_keys": 0,
        "runtime_acceptances": 0,
        "candidate_installations": 0,
        "deployments": 0,
        "hardware_actions": 0,
        "runtime_writes": 0,
    }
    assert report["temporary_fixture_removed"] is True
    assert report["authenticated_fixture_record"]["operator_signature_verified"] is True


def test_preserved_authenticated_acceptance_evidence_replays_exactly():
    preserved = json.loads(
        (
            ROOT / "docs/evidence/aegis-temperature-authenticated-acceptance-v1.json"
        ).read_text()
    )
    assert preserved == run_temperature_authenticated_acceptance_checkride()


def test_live_engine_and_mobile_view_do_not_invent_jt_signature():
    reliability = AegisReliabilityEngine().observe({"operator_guidance": []})
    record = reliability["coverage_development_acceptance"]
    assert reliability["coverage_summary"] == {"total": 8, "trusted": 8, "gaps": 0}
    assert record["status"] == "ACTION_REQUIRED_OPERATOR_CONFIRMATION"
    assert record["operator_signature_present"] is False
    assert record["operator_signature_verified"] is False

    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Authenticated Development Acceptance" in source
    assert "JT SSHSIG:" in source
    assert "private key outside TruePanel" in source
    assert "Deployment authority:" in source
    assert "@media(max-width:760px)" in source
