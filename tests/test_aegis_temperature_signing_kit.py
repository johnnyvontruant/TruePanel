from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from truepanel.aegis.coverage import coverage_matrix
from truepanel.aegis.rehearsal import rehearse_recovery_paths
from truepanel.aegis.ssh_verifier import OpenSshSignatureVerifier
from truepanel.aegis.temperature_authenticated_acceptance import KEY_ID, NAMESPACE
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
from truepanel.aegis.temperature_signing_kit import (
    export_temperature_signing_kit,
    verify_temperature_signing_return,
)
from truepanel.holodeck.aegis_temperature_blind_spot import (
    run_temperature_blind_spot_checkride,
)
from truepanel.holodeck.aegis_temperature_signing_kit import (
    run_temperature_signing_kit_checkride,
)

ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-10-12T04:30:00Z"


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
        "issued_at": "2026-10-12T04:00:00Z",
        "expires_at": "2026-10-13T04:00:00Z",
    }
    return candidate, appraisal, confirmation


def _verifier_and_signature(tmp_path: Path, statement: Path):
    key = tmp_path / "operator"
    subprocess.run(
        ["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
        check=True,
    )
    subprocess.run(
        [
            "/usr/bin/ssh-keygen",
            "-Y",
            "sign",
            "-f",
            str(key),
            "-n",
            NAMESPACE,
            str(statement),
        ],
        check=True,
    )
    signature = Path(f"{statement}.sig")
    os.chmod(signature, 0o600)
    roster = tmp_path / "allowed_signers"
    roster.write_text(
        f"{KEY_ID} {key.with_suffix('.pub').read_text(encoding='ascii')}",
        encoding="ascii",
    )
    os.chmod(roster, 0o600)
    return (
        OpenSshSignatureVerifier(
            roster, namespace=NAMESPACE, expected_key_ids=(KEY_ID,)
        ),
        signature,
    )


def test_public_only_kit_round_trip_reaches_development_review_only(tmp_path):
    candidate, appraisal, confirmation = _materials()
    source = tmp_path / "checkout"
    source.mkdir()
    kit = tmp_path / "public-kit"
    exported = export_temperature_signing_kit(
        candidate,
        appraisal,
        confirmation,
        kit,
        source_root=source,
        now_utc=NOW,
    )
    assert exported["status"] == "READY_FOR_OFFLINE_OPERATOR_SIGNATURE"
    assert {path.name for path in kit.iterdir()} == {
        "statement.json",
        "manifest.json",
        "SIGNING.txt",
    }
    assert exported["private_key_accepted"] is False
    assert exported["signer_invoked"] is False

    verifier, signature = _verifier_and_signature(tmp_path, kit / "statement.json")
    signature.replace(tmp_path / "returned.sig")
    returned = tmp_path / "returned.sig"
    result = verify_temperature_signing_return(
        candidate,
        appraisal,
        confirmation,
        kit,
        returned,
        verifier,
        now_utc=NOW,
    )
    assert result["status"] == "AUTHENTICATED_DEVELOPMENT_ACCEPTED_FOR_REVIEW"
    assert result["operator_signature_verified"] is True
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


def test_export_rejects_checkout_output_and_does_not_leave_partial_kit(tmp_path):
    candidate, appraisal, confirmation = _materials()
    source = tmp_path / "checkout"
    source.mkdir()
    result = export_temperature_signing_kit(
        candidate,
        appraisal,
        confirmation,
        source / "kit",
        source_root=source,
        now_utc=NOW,
    )
    assert result["status"] == "HOLD"
    assert result["kit_created"] is False
    assert not (source / "kit").exists()


def test_return_rejects_tampering_extra_files_and_unsafe_signature(tmp_path):
    candidate, appraisal, confirmation = _materials()
    source = tmp_path / "checkout"
    source.mkdir()
    kit = tmp_path / "public-kit"
    export_temperature_signing_kit(
        candidate,
        appraisal,
        confirmation,
        kit,
        source_root=source,
        now_utc=NOW,
    )
    verifier, signature = _verifier_and_signature(tmp_path, kit / "statement.json")

    (kit / "statement.json").write_bytes((kit / "statement.json").read_bytes() + b" ")
    tampered = verify_temperature_signing_return(
        candidate, appraisal, confirmation, kit, signature, verifier, now_utc=NOW
    )
    assert tampered["status"] == "HOLD"
    assert tampered["operator_signature_verified"] is False

    # A new kit proves the exact-file-set and protected-signature checks separately.
    clean = tmp_path / "clean-kit"
    export_temperature_signing_kit(
        candidate,
        appraisal,
        confirmation,
        clean,
        source_root=source,
        now_utc=NOW,
    )
    (clean / "extra").write_text("unexpected", encoding="ascii")
    extra = verify_temperature_signing_return(
        candidate, appraisal, confirmation, clean, signature, verifier, now_utc=NOW
    )
    assert extra["status"] == "HOLD"
    (clean / "extra").unlink()
    os.chmod(signature, 0o622)
    unsafe = verify_temperature_signing_return(
        candidate, appraisal, confirmation, clean, signature, verifier, now_utc=NOW
    )
    assert unsafe["status"] == "HOLD"


def test_checkride_is_preserved_and_accepts_no_private_key_input():
    report = run_temperature_signing_kit_checkride()
    assert report["measurements"] == {
        "scenario_count": 12,
        "signing_ready_count": 1,
        "authenticated_development_acceptance_count": 1,
        "hold_count": 10,
        "private_key_inputs_accepted": 0,
        "signer_invocations_by_truepanel": 0,
        "fixture_private_keys_created": 1,
        "fixture_private_keys_retained": 0,
        "production_keys": 0,
        "runtime_acceptances": 0,
        "candidate_installations": 0,
        "deployments": 0,
        "hardware_actions": 0,
        "runtime_writes": 0,
    }
    preserved = json.loads(
        (ROOT / "docs/evidence/aegis-temperature-signing-kit-v1.json").read_text()
    )
    assert preserved == report


def test_mobile_view_explains_public_only_offline_ceremony():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()
    assert "Public kit:" in source
    assert "TruePanel never receives the private key" in source
    assert "Return verification:" in source
    assert "@media(max-width:760px)" in source
