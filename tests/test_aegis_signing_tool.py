"""Public-material and safety contracts for the offline signing tool."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from truepanel.aegis.acceptance import semantic_sha256
from truepanel.aegis.development_review import build_development_packet
from truepanel.aegis.operator_handoff import OPERATOR_KEY_ID
from truepanel.aegis.signing_session import SIGNING_SESSION_NAMESPACE
from truepanel.aegis.signing_tool import (
    MATERIALS_SCHEMA,
    audit_signing_kit,
    export_signing_kit,
    load_materials,
    main,
    verify_returned_signature,
)
from truepanel.holodeck.aegis_single_operator_development import (
    NOW,
    development_fixture_materials,
)


def _run(*arguments: str, cwd: Path) -> str:
    return subprocess.run(arguments, cwd=cwd, check=True, capture_output=True, text=True).stdout


def _fixture(tmp_path: Path) -> dict[str, Path]:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    _run("git", "init", "-q", cwd=checkout)
    _run("git", "config", "user.name", "HoloDeck", cwd=checkout)
    _run("git", "config", "user.email", "holodeck@invalid", cwd=checkout)
    (checkout / "subject.txt").write_text("signing tool fixture\n")
    _run("git", "add", "subject.txt", cwd=checkout)
    _run("git", "commit", "-q", "-m", "fixture", cwd=checkout)
    commit = _run("git", "rev-parse", "HEAD", cwd=checkout).strip()

    key = tmp_path / "fixture-key"
    subprocess.run(
        ["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "disposable", "-f", str(key)],
        check=True,
        capture_output=True,
    )
    public = key.with_suffix(".pub").read_text().split()
    roster = tmp_path / "allowed_signers"
    roster.write_text(f"{OPERATOR_KEY_ID} {public[0]} {public[1]}\n")
    os.chmod(roster, 0o600)

    values = development_fixture_materials()
    values["candidate"] = dict(values["candidate"], source_commit=commit)
    values["packet"] = build_development_packet(
        review_id="jt-vega-development-review-v1",
        source_commit=commit,
        policy=values["policy"],
        candidate=values["candidate"],
        holodeck_evidence=values["evidence"],
        coverage_matrix=values["coverage"],
        reviewer_report=values["report"],
    )
    unsigned = deepcopy(values["receipt"])
    unsigned["packet_sha256"] = semantic_sha256(values["packet"])
    unsigned["signature"] = ""
    materials = {
        "schema": MATERIALS_SCHEMA,
        "packet": values["packet"],
        "unsigned_receipt": unsigned,
        "policy": values["policy"],
        "candidate": values["candidate"],
        "holodeck_evidence": values["evidence"],
        "coverage_matrix": values["coverage"],
        "reviewer_report": values["report"],
    }
    materials_path = tmp_path / "materials.json"
    materials_path.write_text(json.dumps(materials))
    return {"checkout": checkout, "key": key, "roster": roster, "materials": materials_path}


def _export(paths: dict[str, Path], output: Path) -> dict:
    return export_signing_kit(
        materials_path=paths["materials"],
        checkout_root=paths["checkout"],
        allowed_signers_path=paths["roster"],
        output_directory=output,
        observed_at="2026-09-19T12:00:00Z",
        unix_seconds=NOW,
        operator_confirmed_utc=True,
    )


def test_export_contains_only_public_content_bound_material(tmp_path):
    paths = _fixture(tmp_path)
    output = tmp_path / "export"

    result = _export(paths, output)

    assert result["status"] == "READY_FOR_OFFLINE_SIGNATURE"
    assert sorted(path.name for path in output.iterdir()) == [
        "README.txt",
        "aegis-development-review.txt",
        "aegis-development-signing-session.json",
        "manifest.json",
    ]
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in output.iterdir())
    assert paths["key"].name not in " ".join(path.read_text() for path in output.iterdir())
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["namespace"] == SIGNING_SESSION_NAMESPACE
    assert manifest["production_authority"] is False
    assert manifest["review_sha256"] == result["review_sha256"]
    audit = audit_signing_kit(output)
    assert audit["status"] == "READY_FOR_OPERATOR_SIGNATURE"
    assert audit["session_sha256"] == result["session_sha256"]


@pytest.mark.parametrize(
    ("target", "replacement", "reason"),
    [
        ("aegis-development-review.txt", b"looks safe\n", "SigningKitPresentationMismatch"),
        ("manifest.json", b"{}", "SigningKitPresentationMismatch"),
        ("README.txt", b"skip the audit\n", "SigningKitPresentationMismatch"),
        (
            "aegis-development-signing-session.json",
            b'{"scope":"DEVELOPMENT_ONLY"}',
            "SigningKitSessionInvalid",
        ),
    ],
)
def test_audit_rejects_transport_and_presentation_substitution(
    tmp_path, target, replacement, reason
):
    paths = _fixture(tmp_path)
    output = tmp_path / "export"
    _export(paths, output)
    (output / target).write_bytes(replacement)

    with pytest.raises(ValueError, match=reason):
        audit_signing_kit(output)


def test_audit_rejects_extra_missing_symlink_and_signature_files(tmp_path):
    paths = _fixture(tmp_path)
    extra = tmp_path / "extra"
    _export(paths, extra)
    (extra / "unexpected.txt").write_text("surprise\n")
    with pytest.raises(ValueError, match="SigningKitLayoutInvalid"):
        audit_signing_kit(extra)

    missing = tmp_path / "missing"
    _export(paths, missing)
    (missing / "README.txt").unlink()
    with pytest.raises(ValueError, match="SigningKitLayoutInvalid"):
        audit_signing_kit(missing)

    linked = tmp_path / "linked"
    _export(paths, linked)
    (linked / "README.txt").unlink()
    (linked / "README.txt").symlink_to(linked / "manifest.json")
    with pytest.raises(ValueError, match="InputPathUnsafe"):
        audit_signing_kit(linked)

    signed = tmp_path / "signed"
    _export(paths, signed)
    (signed / "aegis-development-signing-session.json.sig").write_text("already signed")
    with pytest.raises(ValueError, match="SigningKitLayoutInvalid"):
        audit_signing_kit(signed)


def test_audit_cli_is_public_read_only_and_signer_free(tmp_path, capsys):
    paths = _fixture(tmp_path)
    output = tmp_path / "export"
    _export(paths, output)

    assert main(["audit", "--kit", str(output)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "READY_FOR_OPERATOR_SIGNATURE"
    assert result["production_authority"] is False


def test_returned_real_sshsig_verifies_development_only(tmp_path):
    paths = _fixture(tmp_path)
    output = tmp_path / "export"
    _export(paths, output)
    session = output / "aegis-development-signing-session.json"
    subprocess.run(
        ["/usr/bin/ssh-keygen", "-Y", "sign", "-f", str(paths["key"]), "-n", SIGNING_SESSION_NAMESPACE, str(session)],
        check=True,
        capture_output=True,
    )

    result = verify_returned_signature(
        materials_path=paths["materials"],
        session_path=session,
        signature_path=session.with_suffix(".json.sig"),
        checkout_root=paths["checkout"],
        allowed_signers_path=paths["roster"],
    )

    assert result["status"] == "ELIGIBLE_FOR_DEVELOPMENT_CANDIDATE_REVIEW"
    assert result["production_authority"] is False
    assert result["deployment_authority"] is False
    assert result["hardware_authority"] is False
    assert result["runtime_writes"] == 0


def test_export_rejects_missing_confirmation_and_checkout_output(tmp_path):
    paths = _fixture(tmp_path)
    arguments = {
        "materials_path": paths["materials"],
        "checkout_root": paths["checkout"],
        "allowed_signers_path": paths["roster"],
        "output_directory": tmp_path / "export",
        "observed_at": "2026-09-19T12:00:00Z",
        "unix_seconds": NOW,
        "operator_confirmed_utc": False,
    }
    with pytest.raises(ValueError, match="OperatorUtcConfirmationRequired"):
        export_signing_kit(**arguments)
    arguments["operator_confirmed_utc"] = True
    arguments["output_directory"] = paths["checkout"] / "export"
    with pytest.raises(ValueError, match="OutputInsideCheckoutDenied"):
        export_signing_kit(**arguments)

    checkout_link = tmp_path / "checkout-link"
    checkout_link.symlink_to(paths["checkout"], target_is_directory=True)
    arguments["checkout_root"] = checkout_link
    arguments["output_directory"] = tmp_path / "linked-checkout-export"
    with pytest.raises(ValueError, match="CheckoutPathUnsafe"):
        export_signing_kit(**arguments)


def test_materials_symlink_and_signed_receipt_fail_closed(tmp_path):
    paths = _fixture(tmp_path)
    link = tmp_path / "materials-link.json"
    link.symlink_to(paths["materials"])
    with pytest.raises(ValueError, match="InputPathUnsafe"):
        load_materials(link)
    values = json.loads(paths["materials"].read_text())
    values["unsigned_receipt"]["signature"] = "already-signed"
    paths["materials"].write_text(json.dumps(values))
    with pytest.raises(ValueError, match="SigningMaterialsMustBeUnsigned"):
        load_materials(paths["materials"])


def test_tampered_export_holds_and_cli_never_signs(tmp_path, capsys):
    paths = _fixture(tmp_path)
    output = tmp_path / "export"
    _export(paths, output)
    session = output / "aegis-development-signing-session.json"
    changed = json.loads(session.read_text())
    changed["production_authority"] = True
    session.write_text(json.dumps(changed))
    signature = tmp_path / "returned.sig"
    signature.write_text("not-a-signature")

    result = verify_returned_signature(
        materials_path=paths["materials"],
        session_path=session,
        signature_path=signature,
        checkout_root=paths["checkout"],
        allowed_signers_path=paths["roster"],
    )
    assert result["status"] == "HOLD"
    assert result["reason"] == "SigningSessionMismatch"
    assert main(["export", "--materials", str(paths["materials"]), "--checkout", str(paths["checkout"]), "--allowed-signers", str(paths["roster"]), "--output", str(tmp_path / "second"), "--observed-at", "2026-09-19T12:00:00Z", "--unix-seconds", str(NOW)]) == 2
    assert "OperatorUtcConfirmationRequired" in capsys.readouterr().out


def test_mission_control_names_public_only_offline_ceremony():
    source = (
        Path(__file__).resolve().parents[1]
        / "truepanel/web/static/reliability-view.js"
    ).read_text()
    assert "export public kit · audit review card before signing" in source
    assert "sign outside TruePanel · verify returned signature" in source
    assert "Private key never accepted" in source
    assert "audit review card before signing" in source
