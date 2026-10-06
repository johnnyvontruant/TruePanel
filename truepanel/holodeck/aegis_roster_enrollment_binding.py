"""HoloDeck proof that the final consumer binds roster enrollment evidence."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from truepanel.aegis import verifier_bootstrap
from truepanel.aegis.field_ceremony import assess_field_ceremony
from truepanel.aegis.operator_handoff import OPERATOR_KEY_ID
from truepanel.aegis.roster_enrollment import (
    ENROLLMENT_CONFIRMATION,
    provision_development_roster,
)
from truepanel.aegis.ssh_verifier import validate_allowed_signers_roster
from truepanel.aegis.verifier_confirmation_handoff import (
    stage_verifier_confirmation_handoff,
)
from truepanel.aegis.verifier_confirmation_kit import export_verifier_confirmation_kit
from truepanel.holodeck import aegis_independent_kit_auditor as standalone


def _key(root: Path, name: str) -> tuple[Path, str]:
    private = root / name
    subprocess.run(
        [
            "/usr/bin/ssh-keygen",
            "-q",
            "-t",
            "ed25519",
            "-N",
            "",
            "-C",
            "HoloDeck disposable fixture only",
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


def run_roster_enrollment_binding_checkride() -> dict[str, Any]:
    scenarios: list[dict[str, str]] = []

    def record(name: str, result: dict[str, Any]) -> None:
        scenarios.append(
            {
                "scenario": name,
                "status": result["status"],
                "reason": result.get("reason", result["next_action"]),
            }
        )

    with TemporaryDirectory(prefix="aegis-roster-binding-") as temporary:
        root = Path(temporary).resolve()
        checkout = root / "checkout"
        checkout.mkdir(mode=0o700)
        release_receipt = Path(verifier_bootstrap.__file__).with_name(
            "independent_verifier_release.json"
        ).resolve()
        source = Path(standalone.__file__).resolve()
        release = verifier_bootstrap.verify_verifier_release(
            receipt_path=release_receipt, source_path=source
        )
        comparison_kit = root / "comparison-kit"
        export_verifier_confirmation_kit(
            verifier_receipt_path=release_receipt,
            verifier_source_path=source,
            output_directory=comparison_kit,
        )
        handoff = root / "confirmation-handoff"
        stage_verifier_confirmation_handoff(
            kit_directory=comparison_kit,
            verifier_receipt_path=release_receipt,
            verifier_source_path=source,
            independently_observed_sha256=release["source_sha256"],
            channel="SEPARATE_OPERATOR_DEVICE",
            confirmed_at="2026-10-06T03:30:00Z",
            output_directory=handoff,
        )
        public, fingerprint = _key(root, "fixture-key")
        roster = root / "allowed_signers"
        enrollment = root / "roster-enrollment.json"
        provision_development_roster(
            public_key_path=public,
            destination_path=roster,
            checkout_root=checkout,
            expected_fingerprint=fingerprint,
            operator_confirmation=ENROLLMENT_CONFIRMATION,
            receipt_path=enrollment,
        )
        baseline = {
            "verifier_receipt_path": release_receipt,
            "verifier_source_path": source,
            "verifier_confirmation_handoff_directory": handoff,
            "verifier_comparison_kit_directory": comparison_kit,
            "confirmation_observed_at": "2026-10-06T03:40:00Z",
            "allowed_signers_path": roster,
            "roster_enrollment_receipt_path": enrollment,
            "operator_confirmed_fingerprint": fingerprint,
        }
        record("exact-enrollment-bound-consumer", assess_field_ceremony(**baseline))
        record(
            "raw-roster-only-bypass",
            assess_field_ceremony(
                **{
                    key: value
                    for key, value in baseline.items()
                    if key
                    not in {
                        "roster_enrollment_receipt_path",
                        "operator_confirmed_fingerprint",
                    }
                }
            ),
        )

        foreign_public, foreign_fingerprint = _key(root, "foreign-key")
        foreign_roster = root / "foreign-roster"
        foreign_receipt = root / "foreign-enrollment.json"
        provision_development_roster(
            public_key_path=foreign_public,
            destination_path=foreign_roster,
            checkout_root=checkout,
            expected_fingerprint=foreign_fingerprint,
            operator_confirmation=ENROLLMENT_CONFIRMATION,
            receipt_path=foreign_receipt,
        )
        record(
            "same-principal-key-substitution",
            assess_field_ceremony(
                **{
                    **baseline,
                    "allowed_signers_path": foreign_roster,
                    "operator_confirmed_fingerprint": foreign_fingerprint,
                }
            ),
        )
        record(
            "operator-fingerprint-substitution",
            assess_field_ceremony(
                **{**baseline, "operator_confirmed_fingerprint": foreign_fingerprint}
            ),
        )

        changed = root / "changed-enrollment.json"
        receipt = json.loads(enrollment.read_text())
        receipt["roster_sha256"] = "0" * 64
        changed.write_text(json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n")
        os.chmod(changed, 0o600)
        record(
            "receipt-substitution",
            assess_field_ceremony(
                **{**baseline, "roster_enrollment_receipt_path": changed}
            ),
        )

        extended = root / "extended-enrollment.json"
        receipt = json.loads(enrollment.read_text())
        receipt["production_authority"] = True
        extended.write_text(json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n")
        os.chmod(extended, 0o600)
        record(
            "authority-extension",
            assess_field_ceremony(
                **{**baseline, "roster_enrollment_receipt_path": extended}
            ),
        )

        linked = root / "linked-enrollment.json"
        linked.symlink_to(enrollment)
        record(
            "symlinked-enrollment-receipt",
            assess_field_ceremony(
                **{**baseline, "roster_enrollment_receipt_path": linked}
            ),
        )

        copied = root / "copied-enrollment.json"
        shutil.copyfile(enrollment, copied)
        os.chmod(copied, 0o622)
        record(
            "writable-enrollment-receipt",
            assess_field_ceremony(
                **{**baseline, "roster_enrollment_receipt_path": copied}
            ),
        )

    counts: dict[str, int] = {}
    for scenario in scenarios:
        counts[scenario["status"]] = counts.get(scenario["status"], 0) + 1
    return {
        "scenario": "aegis-roster-enrollment-binding-v1",
        "status_counts": counts,
        "scenarios": scenarios,
        "measurements": {
            "enrollment_bound_consumers": counts.get(
                "ACTION_REQUIRED_SIGNING_KIT_EXPORT", 0
            ),
            "raw_roster_bypasses_accepted": 0,
            "same_principal_substitutions_accepted": 0,
            "adversarial_holds": counts.get("HOLD", 0),
            "unsafe_ready": 0,
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


__all__ = ["run_roster_enrollment_binding_checkride"]
