"""Contracts for public-only AEGIS roster enrollment."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from truepanel.aegis.operator_handoff import OPERATOR_KEY_ID
from truepanel.aegis.roster_enrollment import (
    ENROLLMENT_CONFIRMATION,
    provision_development_roster,
)
from truepanel.aegis.ssh_verifier import validate_allowed_signers_roster
from truepanel.holodeck.aegis_roster_enrollment import (
    run_roster_enrollment_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def _public_key(tmp_path: Path) -> tuple[Path, str]:
    private = tmp_path / "fixture-key"
    subprocess.run(
        [
            "/usr/bin/ssh-keygen",
            "-q",
            "-t",
            "ed25519",
            "-N",
            "",
            "-f",
            str(private),
        ],
        check=True,
        capture_output=True,
    )
    public = private.with_suffix(".pub")
    fields = public.read_text().split()
    roster = f"{OPERATOR_KEY_ID} {fields[0]} {fields[1]}\n".encode()
    fingerprint = validate_allowed_signers_roster(
        roster, expected_key_ids=(OPERATOR_KEY_ID,)
    )[OPERATOR_KEY_ID]
    return public, fingerprint


def test_enrollment_writes_only_one_protected_public_identity(tmp_path):
    checkout = tmp_path / "checkout"
    checkout.mkdir(mode=0o700)
    output = tmp_path / "public-roster"
    output.mkdir(mode=0o700)
    public, fingerprint = _public_key(tmp_path)

    result = provision_development_roster(
        public_key_path=public,
        destination_path=output / "allowed_signers",
        checkout_root=checkout,
        expected_fingerprint=fingerprint,
        operator_confirmation=ENROLLMENT_CONFIRMATION,
    )

    roster = output / "allowed_signers"
    assert result["status"] == "PUBLIC_ROSTER_PROVISIONED_FOR_DEVELOPMENT_REVIEW"
    assert result["key_id"] == OPERATOR_KEY_ID
    assert result["public_key_fingerprint"] == fingerprint
    assert result["private_key_accepted"] is False
    assert result["signer_invoked"] is False
    assert stat_mode(roster) == 0o600
    assert set(validate_allowed_signers_roster(roster.read_bytes())) == {
        OPERATOR_KEY_ID
    }
    assert result["production_authority"] is False
    assert result["deployment_authority"] is False
    assert result["hardware_authority"] is False


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


def test_enrollment_never_overwrites_existing_roster(tmp_path):
    checkout = tmp_path / "checkout"
    checkout.mkdir(mode=0o700)
    public, fingerprint = _public_key(tmp_path)
    destination = tmp_path / "allowed_signers"
    destination.write_text("preserve me\n")

    with pytest.raises(ValueError, match="RosterEnrollmentPathUnsafe"):
        provision_development_roster(
            public_key_path=public,
            destination_path=destination,
            checkout_root=checkout,
            expected_fingerprint=fingerprint,
            operator_confirmation=ENROLLMENT_CONFIRMATION,
        )

    assert destination.read_text() == "preserve me\n"


def test_roster_enrollment_checkride_fails_closed():
    result = run_roster_enrollment_checkride()

    assert result["status_counts"] == {
        "PUBLIC_ROSTER_PROVISIONED_FOR_DEVELOPMENT_REVIEW": 1,
        "READY_FOR_OFFLINE_SIGNATURE": 1,
        "HOLD": 14,
    }
    assert result["measurements"]["unsafe_ready"] == 0
    assert result["measurements"]["private_keys_accepted_by_truepanel"] == 0
    assert result["measurements"]["keys_generated_by_truepanel"] == 0
    assert result["measurements"]["signer_invocations_by_truepanel"] == 0
    assert result["measurements"]["production_acceptances"] == 0
    assert result["control_authority"] is False


def test_preserved_roster_enrollment_evidence_replays_exactly():
    archived = json.loads(
        (ROOT / "docs/evidence/aegis-public-roster-enrollment-v1.json").read_text()
    )
    assert run_roster_enrollment_checkride() == archived


def test_mission_control_names_public_only_roster_boundary():
    source = (ROOT / "truepanel/web/static/reliability-view.js").read_text()

    assert "Roster enrollment · one confirmed Ed25519 public key" in source
    assert "TruePanel never generates or invokes a signer" in source
    assert "Production authority · NO" in source
