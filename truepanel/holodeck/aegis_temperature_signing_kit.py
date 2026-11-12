"""Adversarial public-only signing-kit and return checkride."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

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


def _sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _materials() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
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


def _sign(root: Path, key: Path, statement: Path) -> Path:
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
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    returned = root / "returned.sig"
    Path(f"{statement}.sig").replace(returned)
    os.chmod(returned, 0o600)
    return returned


def run_temperature_signing_kit_checkride() -> dict[str, Any]:
    candidate, appraisal, confirmation = _materials()
    now = "2026-10-12T04:30:00Z"
    scenarios: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    def record(name: str, result: dict[str, Any]) -> None:
        results.append(result)
        scenarios.append(
            {
                "scenario": name,
                "status": result["status"],
                "error_count": len(result["errors"]),
            }
        )

    with tempfile.TemporaryDirectory(prefix="truepanel-temperature-kit-") as directory:
        root = Path(directory)
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
        verifier = OpenSshSignatureVerifier(
            roster, namespace=NAMESPACE, expected_key_ids=(KEY_ID,)
        )

        kit = root / "public-kit"
        exported = export_temperature_signing_kit(
            candidate,
            appraisal,
            confirmation,
            kit,
            source_root=source,
            now_utc=now,
        )
        record("public-only-kit-export", exported)
        signature = _sign(root, key, kit / "statement.json")
        record(
            "exact-returned-sshsig",
            verify_temperature_signing_return(
                candidate,
                appraisal,
                confirmation,
                kit,
                signature,
                verifier,
                now_utc=now,
            ),
        )

        occupied = root / "occupied"
        occupied.mkdir()
        record(
            "occupied-output",
            export_temperature_signing_kit(
                candidate,
                appraisal,
                confirmation,
                occupied,
                source_root=source,
                now_utc=now,
            ),
        )
        record(
            "output-inside-checkout",
            export_temperature_signing_kit(
                candidate,
                appraisal,
                confirmation,
                source / "kit",
                source_root=source,
                now_utc=now,
            ),
        )
        link = root / "kit-link"
        link.symlink_to(kit, target_is_directory=True)
        record(
            "symlinked-kit",
            verify_temperature_signing_return(
                candidate, appraisal, confirmation, link, signature, verifier, now_utc=now
            ),
        )

        statement = kit / "statement.json"
        original_statement = statement.read_bytes()
        statement.write_bytes(original_statement + b" ")
        record(
            "statement-tampering",
            verify_temperature_signing_return(
                candidate, appraisal, confirmation, kit, signature, verifier, now_utc=now
            ),
        )
        statement.write_bytes(original_statement)
        os.chmod(statement, 0o600)

        manifest = kit / "manifest.json"
        original_manifest = manifest.read_bytes()
        changed_manifest = json.loads(original_manifest)
        changed_manifest["deployment_authority"] = True
        manifest.write_text(json.dumps(changed_manifest), encoding="utf-8")
        record(
            "manifest-authority-escalation",
            verify_temperature_signing_return(
                candidate, appraisal, confirmation, kit, signature, verifier, now_utc=now
            ),
        )
        manifest.write_bytes(original_manifest)
        os.chmod(manifest, 0o600)

        extra = kit / "extra"
        extra.write_text("unexpected", encoding="ascii")
        record(
            "unexpected-kit-file",
            verify_temperature_signing_return(
                candidate, appraisal, confirmation, kit, signature, verifier, now_utc=now
            ),
        )
        extra.unlink()

        os.chmod(signature, 0o622)
        record(
            "unsafe-signature-permissions",
            verify_temperature_signing_return(
                candidate, appraisal, confirmation, kit, signature, verifier, now_utc=now
            ),
        )
        os.chmod(signature, 0o600)
        signature_link = root / "returned-link.sig"
        signature_link.symlink_to(signature)
        record(
            "symlinked-signature",
            verify_temperature_signing_return(
                candidate,
                appraisal,
                confirmation,
                kit,
                signature_link,
                verifier,
                now_utc=now,
            ),
        )

        wrong = root / "wrong.sig"
        wrong.write_text("not an ssh signature\n", encoding="ascii")
        os.chmod(wrong, 0o600)
        record(
            "invalid-returned-signature",
            verify_temperature_signing_return(
                candidate, appraisal, confirmation, kit, wrong, verifier, now_utc=now
            ),
        )

        expired = deepcopy(confirmation)
        expired["issued_at"] = "2026-10-10T04:00:00Z"
        expired["expires_at"] = "2026-10-11T04:00:00Z"
        record(
            "expired-confirmation",
            verify_temperature_signing_return(
                candidate, appraisal, expired, kit, signature, verifier, now_utc=now
            ),
        )
        fixture_private_keys_created = 1

    report = {
        "schema_version": 1,
        "experiment_id": "TP-EXP-0027",
        "scenario": "aegis-temperature-public-signing-kit",
        "simulation": True,
        "hardware_isolated": True,
        "production_mutation": False,
        "control_authority": False,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "signing_ready_count": sum(
                result["status"] == "READY_FOR_OFFLINE_OPERATOR_SIGNATURE"
                for result in results
            ),
            "authenticated_development_acceptance_count": sum(
                result["status"] == "AUTHENTICATED_DEVELOPMENT_ACCEPTED_FOR_REVIEW"
                for result in results
            ),
            "hold_count": sum(result["status"] == "HOLD" for result in results),
            "private_key_inputs_accepted": 0,
            "signer_invocations_by_truepanel": 0,
            "fixture_private_keys_created": fixture_private_keys_created,
            "fixture_private_keys_retained": 0,
            "production_keys": 0,
            "runtime_acceptances": 0,
            "candidate_installations": 0,
            "deployments": 0,
            "hardware_actions": 0,
            "runtime_writes": 0,
        },
        "temporary_fixture_removed": not root.exists(),
    }
    report["evidence_sha256"] = _sha256(report)
    return report


__all__ = ["run_temperature_signing_kit_checkride"]
