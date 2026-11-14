"""Real-SSHSIG HoloDeck checkride for temperature development acceptance."""

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
from truepanel.holodeck.aegis_temperature_blind_spot import (
    run_temperature_blind_spot_checkride,
)


def _sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _key(root: Path, name: str) -> Path:
    path = root / name
    subprocess.run(
        ["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(path)],
        check=True,
    )
    return path


def _sign(root: Path, name: str, key: Path, statement: bytes, namespace: str) -> str:
    message = root / name
    message.write_bytes(statement)
    subprocess.run(
        [
            "/usr/bin/ssh-keygen",
            "-Y",
            "sign",
            "-f",
            str(key),
            "-n",
            namespace,
            str(message),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return Path(f"{message}.sig").read_text(encoding="ascii")


def _corrupt_signature(signature: str) -> str:
    lines = signature.splitlines()
    payload_index = 1
    offset = len(lines[payload_index]) // 2
    replacement = "A" if lines[payload_index][offset] != "A" else "B"
    lines[payload_index] = (
        lines[payload_index][:offset] + replacement + lines[payload_index][offset + 1 :]
    )
    return "\n".join(lines) + "\n"


def run_temperature_authenticated_acceptance_checkride() -> dict[str, Any]:
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
    now = "2026-10-11T04:30:00Z"
    statement = build_temperature_acceptance_statement(
        candidate, appraisal, confirmation, now_utc=now
    )

    temporary_removed = False
    with tempfile.TemporaryDirectory(
        prefix="truepanel-aegis-temperature-signature-"
    ) as directory:
        root = Path(directory)
        operator_key = _key(root, "operator")
        foreign_key = _key(root, "foreign")
        roster = root / "allowed_signers"
        roster.write_text(
            f"{KEY_ID} {operator_key.with_suffix('.pub').read_text(encoding='ascii')}",
            encoding="ascii",
        )
        os.chmod(roster, 0o600)
        verifier = OpenSshSignatureVerifier(
            roster, namespace=NAMESPACE, expected_key_ids=(KEY_ID,)
        )
        signature = _sign(root, "exact", operator_key, statement, NAMESPACE)
        wrong_namespace = _sign(
            root, "wrong-namespace", operator_key, statement, "wrong"
        )
        foreign_signature = _sign(
            root, "foreign-signature", foreign_key, statement, NAMESPACE
        )

        cases: list[tuple[str, dict[str, Any] | None, str | None, Any, str]] = [
            ("operator-confirmation-absent", None, None, None, now),
            ("operator-signature-absent", confirmation, None, verifier, now),
            ("exact-operator-sshsig", confirmation, signature, verifier, now),
            (
                "signature-corruption",
                confirmation,
                _corrupt_signature(signature),
                verifier,
                now,
            ),
            ("wrong-signing-namespace", confirmation, wrong_namespace, verifier, now),
            (
                "same-principal-foreign-key",
                confirmation,
                foreign_signature,
                verifier,
                now,
            ),
        ]
        changed = deepcopy(confirmation)
        changed["issued_at"] = "2026-10-11T04:01:00Z"
        cases.append(
            (
                "signature-replay-after-confirmation-change",
                changed,
                signature,
                verifier,
                now,
            )
        )
        expired = deepcopy(confirmation)
        expired["issued_at"] = "2026-10-09T04:00:00Z"
        expired["expires_at"] = "2026-10-10T04:00:00Z"
        cases.append(("expired-confirmation", expired, signature, verifier, now))

        scenarios = []
        results = []
        for name, confirmation_value, signature_value, verifier_value, clock in cases:
            result = evaluate_authenticated_temperature_acceptance(
                candidate,
                appraisal,
                confirmation_value,
                signature_value,
                verifier_value,
                now_utc=clock,
            )
            results.append(result)
            scenarios.append(
                {
                    "scenario": name,
                    "status": result["status"],
                    "error_count": len(result["errors"]),
                }
            )

        def record(name: str, verifier_value: OpenSshSignatureVerifier) -> None:
            result = evaluate_authenticated_temperature_acceptance(
                candidate,
                appraisal,
                confirmation,
                signature,
                verifier_value,
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

        os.chmod(roster, 0o622)
        record(
            "unsafe-roster-permissions",
            OpenSshSignatureVerifier(
                roster, namespace=NAMESPACE, expected_key_ids=(KEY_ID,)
            ),
        )
        os.chmod(roster, 0o600)
        link = root / "roster-link"
        link.symlink_to(roster)
        record(
            "symlinked-roster",
            OpenSshSignatureVerifier(
                link, namespace=NAMESPACE, expected_key_ids=(KEY_ID,)
            ),
        )
        record(
            "verifier-namespace-substitution",
            OpenSshSignatureVerifier(
                roster, namespace="wrong", expected_key_ids=(KEY_ID,)
            ),
        )
        fixture_private_keys = sum(
            path.is_file()
            and path.suffix == ""
            and path.name in {"operator", "foreign"}
            for path in root.iterdir()
        )
    temporary_removed = not root.exists()

    report = {
        "schema_version": 1,
        "experiment_id": "TP-EXP-0026",
        "scenario": "aegis-temperature-authenticated-acceptance",
        "simulation": True,
        "hardware_isolated": True,
        "production_mutation": False,
        "control_authority": False,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "operator_confirmation_required_count": sum(
                r["status"] == "ACTION_REQUIRED_OPERATOR_CONFIRMATION" for r in results
            ),
            "operator_signature_required_count": sum(
                r["status"] == "ACTION_REQUIRED_OPERATOR_SIGNATURE" for r in results
            ),
            "authenticated_development_acceptance_count": sum(
                r["status"] == "AUTHENTICATED_DEVELOPMENT_ACCEPTED_FOR_REVIEW"
                for r in results
            ),
            "hold_count": sum(r["status"] == "HOLD" for r in results),
            "fixture_private_keys_created": fixture_private_keys,
            "fixture_private_keys_retained": 0
            if temporary_removed
            else fixture_private_keys,
            "production_keys": 0,
            "runtime_acceptances": 0,
            "candidate_installations": 0,
            "deployments": 0,
            "hardware_actions": 0,
            "runtime_writes": 0,
        },
        "temporary_fixture_removed": temporary_removed,
        "authenticated_fixture_record": results[2],
    }
    report["evidence_sha256"] = _sha256(report)
    return report


__all__ = ["run_temperature_authenticated_acceptance_checkride"]
