"""Adversarial proof for the content-bound temperature field-review receipt."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from truepanel.aegis.ssh_verifier import OpenSshSignatureVerifier
from truepanel.aegis.temperature_authenticated_acceptance import (
    KEY_ID,
)
from truepanel.aegis.temperature_authenticated_acceptance import (
    NAMESPACE as DEVELOPMENT_NAMESPACE,
)
from truepanel.aegis.temperature_field_review_receipt import (
    NAMESPACE as REVIEW_NAMESPACE,
)
from truepanel.aegis.temperature_field_review_receipt import (
    evaluate_temperature_field_review_receipt,
    export_temperature_field_review_kit,
)
from truepanel.aegis.temperature_signing_kit import export_temperature_signing_kit
from truepanel.holodeck.aegis_temperature_field_checkride import _frames
from truepanel.holodeck.aegis_temperature_recording_intake import _write_recording
from truepanel.holodeck.aegis_temperature_signing_kit import _materials


def _sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _sign(key: Path, statement: Path, destination: Path, namespace: str) -> None:
    subprocess.run(
        [
            "/usr/bin/ssh-keygen",
            "-Y",
            "sign",
            "-f",
            str(key),
            "-n",
            namespace,
            str(statement),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    Path(f"{statement}.sig").replace(destination)
    os.chmod(destination, 0o600)


def run_temperature_field_review_receipt_checkride() -> dict[str, Any]:
    """Prove exact-subject review and strict non-production authority."""

    candidate, appraisal, confirmation = _materials()
    prepared = "2026-10-12T04:30:00Z"
    expires = "2026-10-12T05:30:00Z"
    scenarios: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="truepanel-temperature-review-") as directory:
        root = Path(directory).resolve()
        source = root / "checkout"
        source.mkdir()
        key = root / "fixture-key"
        subprocess.run(
            ["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
            check=True,
        )
        roster = root / "allowed_signers"
        roster.write_text(
            f"{KEY_ID} {key.with_suffix('.pub').read_text(encoding='ascii')}",
            encoding="ascii",
        )
        os.chmod(roster, 0o600)
        development_verifier = OpenSshSignatureVerifier(
            roster, namespace=DEVELOPMENT_NAMESPACE, expected_key_ids=(KEY_ID,)
        )
        review_verifier = OpenSshSignatureVerifier(
            roster, namespace=REVIEW_NAMESPACE, expected_key_ids=(KEY_ID,)
        )
        development_kit = root / "development-kit"
        export_temperature_signing_kit(
            candidate,
            appraisal,
            confirmation,
            development_kit,
            source_root=source,
            now_utc=prepared,
        )
        development_signature = root / "development.sig"
        _sign(
            key,
            development_kit / "statement.json",
            development_signature,
            DEVELOPMENT_NAMESPACE,
        )
        recording = root / "recording.jsonl"
        _write_recording(recording, _frames())
        review_kit = root / "review-kit"
        export_result = export_temperature_field_review_kit(
            candidate,
            appraisal,
            confirmation,
            development_kit,
            development_signature,
            development_verifier,
            recording,
            review_kit,
            source_root=source,
            prepared_at_utc=prepared,
            expires_at_utc=expires,
            now_utc=prepared,
        )
        results.append(export_result)
        scenarios.append(
            {
                "scenario": "public-only-review-kit",
                "status": export_result["status"],
                "error_count": len(export_result["errors"]),
            }
        )
        review_signature = root / "review.sig"
        _sign(
            key,
            review_kit / "field-review-statement.json",
            review_signature,
            REVIEW_NAMESPACE,
        )

        def run(
            name: str,
            *,
            kit: Path = review_kit,
            signature: Path = review_signature,
            verifier: Any = review_verifier,
            recording_path: Path = recording,
            now: str = prepared,
        ) -> dict[str, Any]:
            result = evaluate_temperature_field_review_receipt(
                candidate,
                appraisal,
                confirmation,
                development_kit,
                development_signature,
                development_verifier,
                recording_path,
                kit,
                signature,
                verifier,
                prepared_at_utc=prepared,
                expires_at_utc=expires,
                now_utc=now,
            )
            results.append(result)
            scenarios.append(
                {
                    "scenario": name,
                    "status": result["status"],
                    "error_count": len(result["errors"]),
                }
            )
            return result

        run("content-bound-field-review")
        run("delayed-review-within-window", now="2026-10-12T05:00:00Z")

        wrong_namespace_signature = root / "wrong-namespace.sig"
        _sign(
            key,
            review_kit / "field-review-statement.json",
            wrong_namespace_signature,
            DEVELOPMENT_NAMESPACE,
        )
        run("wrong-signature-namespace", signature=wrong_namespace_signature)

        foreign_key = root / "foreign-key"
        subprocess.run(
            [
                "/usr/bin/ssh-keygen",
                "-q",
                "-t",
                "ed25519",
                "-N",
                "",
                "-f",
                str(foreign_key),
            ],
            check=True,
        )
        foreign_roster = root / "foreign_allowed_signers"
        foreign_roster.write_text(
            f"{KEY_ID} {foreign_key.with_suffix('.pub').read_text(encoding='ascii')}",
            encoding="ascii",
        )
        os.chmod(foreign_roster, 0o600)
        foreign_verifier = OpenSshSignatureVerifier(
            foreign_roster, namespace=REVIEW_NAMESPACE, expected_key_ids=(KEY_ID,)
        )
        foreign_signature = root / "foreign.sig"
        _sign(
            foreign_key,
            review_kit / "field-review-statement.json",
            foreign_signature,
            REVIEW_NAMESPACE,
        )
        run(
            "same-principal-foreign-trust-root",
            signature=foreign_signature,
            verifier=foreign_verifier,
        )

        invalid_signature = root / "invalid.sig"
        invalid_signature.write_text("not an ssh signature\n", encoding="ascii")
        os.chmod(invalid_signature, 0o600)
        run("invalid-review-signature", signature=invalid_signature)

        changed_recording = root / "changed-recording.jsonl"
        changed_frames = deepcopy(_frames())
        changed_frames[1]["captured_at"] = 100.0
        _write_recording(changed_recording, changed_frames)
        run("recording-changed-after-export", recording_path=changed_recording)

        def kit_copy(name: str) -> Path:
            destination = root / name
            shutil.copytree(review_kit, destination)
            return destination

        tampered_statement = kit_copy("tampered-statement-kit")
        statement_path = tampered_statement / "field-review-statement.json"
        statement = json.loads(statement_path.read_text())
        statement["hardware_authority"] = True
        statement_path.write_text(json.dumps(statement), encoding="utf-8")
        os.chmod(statement_path, 0o600)
        run("authority-escalation", kit=tampered_statement)

        tampered_manifest = kit_copy("tampered-manifest-kit")
        manifest_path = tampered_manifest / "manifest.json"
        manifest_path.write_text("{}\n", encoding="utf-8")
        os.chmod(manifest_path, 0o600)
        run("manifest-substitution", kit=tampered_manifest)

        unsafe_kit = kit_copy("unsafe-permissions-kit")
        os.chmod(unsafe_kit / "field-review-statement.json", 0o666)
        run("unsafe-statement-permissions", kit=unsafe_kit)

        extra_file_kit = kit_copy("extra-file-kit")
        (extra_file_kit / "unexpected.txt").write_text("unexpected\n")
        run("unexpected-kit-file", kit=extra_file_kit)

        run("expired-review-window", now="2026-10-12T05:31:00Z")

        paths_retained = sum(str(root) in json.dumps(item) for item in results)

    report = {
        "schema_version": 1,
        "experiment_id": "TP-EXP-0030",
        "scenario": "aegis-content-bound-temperature-field-review-receipt",
        "simulation": True,
        "hardware_isolated": True,
        "production_mutation": False,
        "control_authority": False,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "signing_ready_count": sum(
                item["status"] == "READY_FOR_OFFLINE_FIELD_REVIEW_SIGNATURE"
                for item in results
            ),
            "field_review_accepted_count": sum(
                item["status"] == "FIELD_OBSERVATION_ACCEPTED_FOR_REVIEW"
                for item in results
            ),
            "hold_count": sum(item["status"] == "HOLD" for item in results),
            "unsafe_ready_count": sum(
                item["status"] != "HOLD" for item in results[3:]
            ),
            "source_paths_retained": paths_retained,
            "private_key_inputs": sum(
                item["private_key_accepted"] is not False for item in results
            ),
            "signer_invocations_by_truepanel": sum(
                item["signer_invoked"] is not False for item in results
            ),
            "fixture_private_keys_created": 2,
            "fixture_private_keys_retained": 0,
            "field_validations": 0,
            "candidate_acceptances": 0,
            "candidate_installations": 0,
            "deployments": 0,
            "hardware_actions": 0,
            "runtime_writes": 0,
        },
        "comparison": {
            "before": "caller booleans could describe opt-in and outcome review without a content-bound operator receipt",
            "after": "one offline SSHSIG binds the exact recording, privacy and outcome review, expiry, development identity, and zero authority",
            "result": "review intent is machine-verifiable while calibration use remains review-only",
        },
        "temporary_fixture_removed": not root.exists(),
    }
    report["evidence_sha256"] = _sha256(report)
    return report


__all__ = ["run_temperature_field_review_receipt_checkride"]
