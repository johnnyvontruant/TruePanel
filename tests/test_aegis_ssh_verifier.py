import json
import os
import subprocess
from pathlib import Path

import truepanel.aegis.ssh_verifier as verifier_module
from truepanel.aegis.ssh_verifier import DEFAULT_NAMESPACE, OpenSshSignatureVerifier
from truepanel.holodeck.aegis_offline_signature import (
    run_offline_signature_checkride,
)

ROOT = Path(__file__).resolve().parents[1]


def _key_and_signature(tmp_path: Path, statement: bytes):
    key = tmp_path / "reviewer"
    subprocess.run(
        ["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
        check=True,
    )
    message = tmp_path / "statement"
    message.write_bytes(statement)
    subprocess.run(
        [
            "/usr/bin/ssh-keygen",
            "-Y",
            "sign",
            "-f",
            str(key),
            "-n",
            DEFAULT_NAMESPACE,
            str(message),
        ],
        check=True,
    )
    allowed = tmp_path / "allowed_signers"
    allowed.write_text(
        "reviewer-a " + key.with_suffix(".pub").read_text(encoding="ascii"),
        encoding="ascii",
    )
    os.chmod(allowed, 0o600)
    signature = Path(f"{message}.sig").read_text(encoding="ascii")
    return allowed, signature


def test_openssh_verifier_accepts_exact_statement(tmp_path):
    statement = b'{"request":"exact"}'
    allowed, signature = _key_and_signature(tmp_path, statement)
    verifier = OpenSshSignatureVerifier(allowed)

    assert verifier("reviewer-a", statement, signature) is True
    assert verifier("reviewer-a", statement + b"-changed", signature) is False
    assert verifier("other-reviewer", statement, signature) is False


def test_openssh_verifier_rejects_unsafe_trust_file(tmp_path):
    statement = b"bounded statement"
    allowed, signature = _key_and_signature(tmp_path, statement)
    os.chmod(allowed, 0o622)

    assert OpenSshSignatureVerifier(allowed)("reviewer-a", statement, signature) is False


def test_openssh_verifier_rejects_symlinked_trust_file(tmp_path):
    statement = b"bounded statement"
    allowed, signature = _key_and_signature(tmp_path, statement)
    link = tmp_path / "allowed_signers_link"
    link.symlink_to(allowed)

    assert OpenSshSignatureVerifier(link)("reviewer-a", statement, signature) is False


def test_openssh_verifier_requires_absolute_executable(tmp_path):
    statement = b"bounded statement"
    allowed, signature = _key_and_signature(tmp_path, statement)

    verifier = OpenSshSignatureVerifier(allowed, executable="ssh-keygen")
    assert verifier("reviewer-a", statement, signature) is False


def test_openssh_verifier_fails_closed_without_memfd(tmp_path, monkeypatch):
    statement = b"bounded statement"
    allowed, signature = _key_and_signature(tmp_path, statement)
    monkeypatch.delattr(verifier_module.os, "memfd_create")

    assert OpenSshSignatureVerifier(allowed)("reviewer-a", statement, signature) is False


def test_full_offline_checkride_stops_before_promotion():
    report = run_offline_signature_checkride()

    assert report["status_counts"] == {"READY_FOR_MANUAL_PROMOTION": 1, "HOLD": 9}
    assert report["measurements"] == {
        "false_ready_paths": 0,
        "private_keys_persisted": 0,
        "production_signers_present": 0,
        "promotion_confirmations_supplied": 0,
        "promotion_executions": 0,
        "receipt_consumptions": 0,
        "service_changes": 0,
        "runtime_writes": 0,
    }
    assert report["temporary_fixture_removed"] is True
    assert report["production_mutation"] is False
    assert report["control_authority"] is False


def test_preserved_offline_signature_evidence_replays_exactly():
    archived = json.loads(
        (ROOT / "docs/evidence/aegis-offline-signature-checkride-v1.json").read_text(
            encoding="utf-8"
        )
    )

    assert run_offline_signature_checkride() == archived
