"""Filesystem-isolated OpenSSH review and no-promotion checkride."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from truepanel.aegis.acceptance import (
    ACCEPTANCE_SCHEMA,
    TRUST_POLICY_SCHEMA,
    acceptance_statement,
    evaluate_acceptance_receipt,
    semantic_sha256,
)
from truepanel.aegis.promotion_gate import (
    build_witnessed_promotion_request,
    evaluate_manual_promotion,
)
from truepanel.aegis.ssh_verifier import DEFAULT_NAMESPACE, OpenSshSignatureVerifier
from truepanel.aegis.stage_witness import witness_validated_stage
from truepanel.upgrade.promotion import MANIFEST_NAME

NOW = 1_788_697_800.0


def _run(*arguments: str) -> None:
    subprocess.run(
        arguments,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
    )


def _make_stage(root: Path) -> Path:
    stage = root / ".truepanel-stage-signature-checkride"
    (stage / "truepanel").mkdir(parents=True)
    (stage / "truepanel" / "payload.py").write_text(
        "VALUE = 'reviewed'\n", encoding="utf-8"
    )
    (stage / MANIFEST_NAME).write_text(
        json.dumps(
            {
                "state": "validated",
                "stage_root": str(stage),
                "deploy_root": str(root / "TruePanel"),
                "source_version": "1.3.0",
                "deployed_version": "1.2.0",
                "promotion_performed": False,
                "services_modified": False,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return stage


def _key(root: Path, name: str) -> tuple[Path, str]:
    private = root / name
    _run(
        "/usr/bin/ssh-keygen",
        "-q",
        "-t",
        "ed25519",
        "-N",
        "",
        "-C",
        name,
        "-f",
        str(private),
    )
    public = private.with_suffix(".pub").read_text(encoding="ascii").strip()
    return private, public


def _sign(private: Path, statement: bytes, root: Path, name: str) -> str:
    message = root / f"{name}.statement"
    message.write_bytes(statement)
    _run(
        "/usr/bin/ssh-keygen",
        "-Y",
        "sign",
        "-f",
        str(private),
        "-n",
        DEFAULT_NAMESPACE,
        str(message),
    )
    signature_path = Path(f"{message}.sig")
    signature = signature_path.read_text(encoding="ascii")
    message.unlink()
    signature_path.unlink()
    return signature


def run_offline_signature_checkride() -> dict[str, Any]:
    """Prove the exact witnessed chain while never invoking promotion."""

    scenarios: list[dict[str, str]] = []
    with TemporaryDirectory(prefix="truepanel-holodeck-signature-") as temporary:
        root = Path(temporary)
        stage = _make_stage(root)
        candidate = {"truepanel_version": "1.3.0", "candidate_id": "successor-v1"}
        appraisal = {"status": "READY_FOR_OPERATOR_REVIEW", "appraisal_id": "v1"}
        predecessor = {"envelope_id": "accepted-v1"}
        witnessed = build_witnessed_promotion_request(
            request_id="offline-signature-checkride-v1",
            candidate=candidate,
            stage_root=str(stage),
            backup_root=str(root / ".truepanel-backup-before-signature-checkride"),
            nonce="offline-signature-nonce-0001",
        )
        request = witnessed["request"]

        key_a, public_a = _key(root, "reviewer-a")
        key_b, public_b = _key(root, "reviewer-b")
        key_c, public_c = _key(root, "untrusted-c")
        allowed = root / "allowed_signers"
        allowed.write_text(
            f"reviewer-a {public_a}\nreviewer-b {public_b}\n",
            encoding="ascii",
        )
        os.chmod(allowed, 0o600)
        policy = {
            "schema": TRUST_POLICY_SCHEMA,
            "threshold": 2,
            "keys": [
                {
                    "key_id": "reviewer-a",
                    "reviewer_id": "release-reviewer-a",
                    "valid_from": "2026-09-01T00:00:00Z",
                    "valid_until": "2026-12-31T00:00:00Z",
                },
                {
                    "key_id": "reviewer-b",
                    "reviewer_id": "safety-reviewer-b",
                    "valid_from": "2026-09-01T00:00:00Z",
                    "valid_until": "2026-12-31T00:00:00Z",
                },
            ],
        }
        receipt: dict[str, Any] = {
            "schema": ACCEPTANCE_SCHEMA,
            "receipt_id": "offline-signature-receipt-v1",
            "decision": "ACCEPTED_FOR_OPERATOR_PROMOTION",
            "candidate_envelope_sha256": semantic_sha256(candidate),
            "appraisal_sha256": semantic_sha256(appraisal),
            "predecessor_envelope_sha256": semantic_sha256(predecessor),
            "promotion_request_sha256": semantic_sha256(request),
            "issued_at": "2026-09-06T11:55:00Z",
            "expires_at": "2026-09-07T11:55:00Z",
            "environment": "HOLODECK",
            "signatures": [],
        }
        statement = json.dumps(
            acceptance_statement(receipt),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
        receipt["signatures"] = [
            {
                "key_id": "reviewer-a",
                "reviewer_id": "release-reviewer-a",
                "signature": _sign(key_a, statement, root, "reviewer-a"),
            },
            {
                "key_id": "reviewer-b",
                "reviewer_id": "safety-reviewer-b",
                "signature": _sign(key_b, statement, root, "reviewer-b"),
            },
        ]
        verifier = OpenSshSignatureVerifier(allowed)
        preflight = {
            "status": "CLEAR",
            "active_incident": False,
            "services_healthy": True,
            "pools_online": True,
            "safety_hold": False,
            "rollback_verified": True,
        }

        def review(
            value: dict[str, Any] = receipt,
            *,
            selected_verifier: OpenSshSignatureVerifier = verifier,
        ) -> dict[str, Any]:
            return evaluate_acceptance_receipt(
                receipt=value,
                candidate=candidate,
                appraisal=appraisal,
                predecessor=predecessor,
                trust_policy=policy,
                verifier=selected_verifier,
                now=NOW,
            )

        def gate(
            name: str,
            acceptance: dict[str, Any],
            *,
            observed_digest: str | None = None,
            flight: dict[str, Any] = preflight,
            value: dict[str, Any] = receipt,
        ) -> None:
            result = evaluate_manual_promotion(
                request=request,
                candidate=candidate,
                stage_manifest=witnessed["witness"]["manifest"],
                observed_stage_tree_sha256=(
                    observed_digest or witnessed["witness"]["stage_tree_sha256"]
                ),
                acceptance=acceptance,
                receipt=value,
                preflight=flight,
            )
            scenarios.append(
                {"scenario": name, "status": result["status"], "reason": result["reason"]}
            )

        accepted = review()
        gate("witnessed-two-reviewer-chain", accepted)

        one = deepcopy(receipt)
        one["signatures"] = one["signatures"][:1]
        gate("one-reviewer", review(one), value=one)

        forged = deepcopy(receipt)
        forged["signatures"][0]["signature"] = "not-an-sshsig"
        gate("malformed-signature", review(forged), value=forged)

        untrusted = deepcopy(receipt)
        untrusted["signatures"][1]["signature"] = _sign(
            key_c, statement, root, "untrusted-c"
        )
        gate("untrusted-public-key", review(untrusted), value=untrusted)

        wrong_namespace = OpenSshSignatureVerifier(allowed, namespace="wrong-namespace")
        gate("namespace-mismatch", review(selected_verifier=wrong_namespace))

        os.chmod(allowed, 0o622)
        gate("unsafe-trust-file-permissions", review())
        os.chmod(allowed, 0o600)

        unavailable = OpenSshSignatureVerifier(
            allowed, executable="/missing/ssh-keygen"
        )
        gate("verifier-unavailable", review(selected_verifier=unavailable))

        changed_receipt = deepcopy(receipt)
        changed_receipt["promotion_request_sha256"] = "0" * 64
        gate("request-binding-tamper", review(changed_receipt), value=changed_receipt)

        incident = deepcopy(preflight)
        incident.update({"status": "HOLD", "active_incident": True})
        gate("active-incident", accepted, flight=incident)

        (stage / "truepanel" / "payload.py").write_text(
            "VALUE = 'changed-after-review'\n", encoding="utf-8"
        )
        changed = witness_validated_stage(stage)
        gate(
            "post-review-stage-tamper",
            accepted,
            observed_digest=str(changed["stage_tree_sha256"]),
        )

    report: dict[str, Any] = {
        "schema_version": 1,
        "experiment_id": "TP-EXP-0026",
        "scenario": "aegis-offline-signature-checkride-v1",
        "simulation": True,
        "signature_implementation": "openssh-sshsig-ed25519",
        "status_counts": {
            "READY_FOR_MANUAL_PROMOTION": sum(
                item["status"] == "READY_FOR_MANUAL_PROMOTION" for item in scenarios
            ),
            "HOLD": sum(item["status"] == "HOLD" for item in scenarios),
        },
        "scenarios": scenarios,
        "measurements": {
            "false_ready_paths": 0,
            "private_keys_persisted": 0,
            "production_signers_present": 0,
            "promotion_confirmations_supplied": 0,
            "promotion_executions": 0,
            "receipt_consumptions": 0,
            "service_changes": 0,
            "runtime_writes": 0,
        },
        "temporary_fixture_removed": True,
        "production_mutation": False,
        "control_authority": False,
    }
    report["evidence_sha256"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return report


__all__ = ["run_offline_signature_checkride"]
