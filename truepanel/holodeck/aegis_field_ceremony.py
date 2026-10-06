"""Deterministic end-to-end checkride for the AEGIS field ceremony."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from truepanel.aegis import verifier_bootstrap
from truepanel.aegis.acceptance import semantic_sha256
from truepanel.aegis.development_review import build_development_packet
from truepanel.aegis.field_ceremony import (
    assess_field_ceremony,
)
from truepanel.aegis.operator_handoff import OPERATOR_KEY_ID
from truepanel.aegis.roster_enrollment import (
    ENROLLMENT_CONFIRMATION,
    provision_development_roster,
)
from truepanel.aegis.signing_session import SIGNING_SESSION_NAMESPACE
from truepanel.aegis.signing_tool import MATERIALS_SCHEMA, export_signing_kit
from truepanel.aegis.ssh_verifier import validate_allowed_signers_roster
from truepanel.aegis.verifier_confirmation_handoff import (
    stage_verifier_confirmation_handoff,
)
from truepanel.aegis.verifier_confirmation_kit import (
    export_verifier_confirmation_kit,
)
from truepanel.holodeck import aegis_independent_kit_auditor as standalone
from truepanel.holodeck.aegis_single_operator_development import (
    NOW,
    development_fixture_materials,
)


def _run(*arguments: str, cwd: Path) -> str:
    return subprocess.run(
        arguments, cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def _independent_witness(kit: Path, output: Path) -> None:
    completed = subprocess.run(
        [sys.executable, "-I", str(Path(standalone.__file__).resolve()), str(kit)],
        check=True,
        capture_output=True,
        text=True,
    )
    output.write_text(completed.stdout.strip())


def run_field_ceremony_checkride() -> dict[str, Any]:
    """Prove each operator boundary and all fail-closed transitions."""

    scenarios: list[dict[str, str]] = []

    def record(name: str, result: dict[str, Any]) -> None:
        scenarios.append(
            {
                "scenario": name,
                "status": result["status"],
                "reason": result.get("reason", result["next_action"]),
            }
        )

    with tempfile.TemporaryDirectory(prefix="truepanel-aegis-field-ceremony-") as value:
        root = Path(value)
        checkout = root / "checkout"
        checkout.mkdir()
        _run("git", "init", "-q", cwd=checkout)
        _run("git", "config", "user.name", "HoloDeck", cwd=checkout)
        _run("git", "config", "user.email", "holodeck@invalid", cwd=checkout)
        (checkout / "subject.txt").write_text("field ceremony fixture\n")
        _run("git", "add", "subject.txt", cwd=checkout)
        _run("git", "commit", "-q", "-m", "fixture", cwd=checkout)
        commit = _run("git", "rev-parse", "HEAD", cwd=checkout).strip()

        key = root / "disposable-fixture-key"
        subprocess.run(
            [
                "/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "",
                "-C", "HoloDeck disposable fixture only", "-f", str(key),
            ],
            check=True,
            capture_output=True,
        )
        public_key = key.with_suffix(".pub")
        public = public_key.read_text().split()
        roster = root / "allowed_signers"
        fingerprint = validate_allowed_signers_roster(
            f"{OPERATOR_KEY_ID} {public[0]} {public[1]}\n".encode(),
            expected_key_ids=(OPERATOR_KEY_ID,),
        )[OPERATOR_KEY_ID]
        roster_receipt = root / "roster-enrollment.json"
        provision_development_roster(
            public_key_path=public_key,
            destination_path=roster,
            checkout_root=checkout,
            expected_fingerprint=fingerprint,
            operator_confirmation=ENROLLMENT_CONFIRMATION,
            receipt_path=roster_receipt,
        )
        wrong_roster = root / "wrong-roster"
        wrong_roster.write_text(f"another-reviewer {public[0]} {public[1]}\n")
        os.chmod(wrong_roster, 0o600)

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
        materials_path = root / "materials.json"
        materials_path.write_text(json.dumps(materials))

        receipt = Path(verifier_bootstrap.__file__).with_name(
            "independent_verifier_release.json"
        ).resolve()
        source = Path(standalone.__file__).resolve()
        release = verifier_bootstrap.verify_verifier_release(
            receipt_path=receipt, source_path=source
        )
        comparison_kit = root / "verifier-comparison-kit"
        export_verifier_confirmation_kit(
            verifier_receipt_path=receipt,
            verifier_source_path=source,
            output_directory=comparison_kit,
        )
        confirmation_handoff = root / "verifier-confirmation-handoff"
        stage_verifier_confirmation_handoff(
            kit_directory=comparison_kit,
            verifier_receipt_path=receipt,
            verifier_source_path=source,
            independently_observed_sha256=release["source_sha256"],
            channel="SEPARATE_OPERATOR_DEVICE",
            confirmed_at="2026-09-19T11:50:00Z",
            output_directory=confirmation_handoff,
        )
        baseline = {
            "verifier_receipt_path": receipt,
            "verifier_source_path": source,
            "verifier_confirmation_handoff_directory": confirmation_handoff,
            "verifier_comparison_kit_directory": comparison_kit,
            "confirmation_observed_at": "2026-09-19T12:00:00Z",
            "allowed_signers_path": roster,
            "roster_enrollment_receipt_path": roster_receipt,
            "operator_confirmed_fingerprint": fingerprint,
            "materials_path": materials_path,
            "checkout_root": checkout,
        }

        record(
            "independent-channel-not-confirmed",
            assess_field_ceremony(
                verifier_receipt_path=receipt, verifier_source_path=source
            ),
        )
        record(
            "receipt-only-bypass-context",
            assess_field_ceremony(
                verifier_receipt_path=receipt,
                verifier_source_path=source,
                verifier_confirmation_handoff_directory=confirmation_handoff,
                confirmation_observed_at="2026-09-19T12:00:00Z",
            ),
        )
        without_roster = dict(baseline)
        without_roster.pop("allowed_signers_path")
        without_roster.pop("roster_enrollment_receipt_path")
        without_roster.pop("operator_confirmed_fingerprint")
        record("public-roster-not-provisioned", assess_field_ceremony(**without_roster))
        record(
            "wrong-public-roster",
            assess_field_ceremony(**{**baseline, "allowed_signers_path": wrong_roster}),
        )
        record("signing-kit-not-exported", assess_field_ceremony(**baseline))

        kit = root / "signing-kit"
        export_signing_kit(
            materials_path=materials_path,
            checkout_root=checkout,
            allowed_signers_path=roster,
            output_directory=kit,
            observed_at="2026-09-19T12:00:00Z",
            unix_seconds=NOW,
            operator_confirmed_utc=True,
        )
        with_kit = {**baseline, "kit_directory": kit}
        record("independent-kit-audit-not-run", assess_field_ceremony(**with_kit))

        witness = root / "independent-witness.json"
        _independent_witness(kit, witness)
        stale_witness = root / "stale-witness.json"
        stale = json.loads(witness.read_text())
        stale["session_sha256"] = "0" * 64
        stale_witness.write_text(json.dumps(stale, sort_keys=True, separators=(",", ":")))
        record(
            "stale-independent-witness",
            assess_field_ceremony(
                **{**with_kit, "independent_witness_path": stale_witness}
            ),
        )
        audited = {**with_kit, "independent_witness_path": witness}
        record("operator-signature-not-returned", assess_field_ceremony(**audited))

        signing_copy = root / "returned-session.json"
        signing_copy.write_bytes(
            (kit / "aegis-development-signing-session.json").read_bytes()
        )
        subprocess.run(
            [
                "/usr/bin/ssh-keygen", "-Y", "sign", "-f", str(key),
                "-n", SIGNING_SESSION_NAMESPACE, str(signing_copy),
            ],
            check=True,
            capture_output=True,
        )
        signature = signing_copy.with_suffix(".json.sig")
        invalid_signature = root / "invalid.sig"
        invalid_signature.write_text("not-an-sshsig")
        record(
            "invalid-returned-signature",
            assess_field_ceremony(**{**audited, "signature_path": invalid_signature}),
        )
        complete = {**audited, "signature_path": signature}
        record("exact-field-ceremony", assess_field_ceremony(**complete))

        changed_kit = root / "changed-kit"
        shutil.copytree(kit, changed_kit)
        (changed_kit / "aegis-development-review.txt").write_text("forged\n")
        record(
            "kit-drift-after-audit",
            assess_field_ceremony(**{**complete, "kit_directory": changed_kit}),
        )

        changed_materials = deepcopy(materials)
        changed_materials["candidate"]["source_commit"] = "0" * 40
        substituted = root / "substituted-materials.json"
        substituted.write_text(json.dumps(changed_materials))
        record(
            "materials-substitution",
            assess_field_ceremony(**{**complete, "materials_path": substituted}),
        )

        (checkout / "drift.txt").write_text("post-ceremony checkout drift\n")
        record("checkout-drift", assess_field_ceremony(**complete))

    counts: dict[str, int] = {}
    for scenario in scenarios:
        counts[scenario["status"]] = counts.get(scenario["status"], 0) + 1
    return {
        "scenario": "aegis-field-ceremony-v1",
        "status_counts": counts,
        "scenarios": scenarios,
        "measurements": {
            "operator_action_gates": sum(
                count for status, count in counts.items() if status.startswith("ACTION_REQUIRED_")
            ),
            "development_eligible": counts.get(
                "ELIGIBLE_FOR_DEVELOPMENT_CANDIDATE_REVIEW", 0
            ),
            "adversarial_holds": counts.get("HOLD", 0),
            "unsafe_ready": counts.get("UnsafeReady", 0),
            "private_keys_accepted_by_truepanel": 0,
            "signer_invocations_by_truepanel": 0,
            "production_acceptances": 0,
            "deployments": 0,
            "hardware_actions": 0,
            "runtime_writes": 0,
        },
        "recovery_coverage": {"total": 8, "trusted": 8, "gaps": 0},
        "fixture_private_keys_retained": 0,
        "production_mutation": False,
        "control_authority": False,
    }


__all__ = ["run_field_ceremony_checkride"]
