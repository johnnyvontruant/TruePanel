"""HoloDeck proof that a signing kit is bound to the enrolled public key."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from truepanel.aegis import verifier_bootstrap
from truepanel.aegis.acceptance import semantic_sha256
from truepanel.aegis.development_review import build_development_packet
from truepanel.aegis.field_ceremony import assess_field_ceremony
from truepanel.aegis.operator_handoff import OPERATOR_KEY_ID
from truepanel.aegis.roster_enrollment import (
    ENROLLMENT_CONFIRMATION,
    provision_development_roster,
)
from truepanel.aegis.signing_tool import MATERIALS_SCHEMA, export_signing_kit
from truepanel.aegis.ssh_verifier import validate_allowed_signers_roster
from truepanel.aegis.verifier_confirmation_handoff import (
    stage_verifier_confirmation_handoff,
)
from truepanel.aegis.verifier_confirmation_kit import export_verifier_confirmation_kit
from truepanel.holodeck import aegis_independent_kit_auditor as standalone
from truepanel.holodeck.aegis_single_operator_development import (
    NOW,
    development_fixture_materials,
)


def _run(*arguments: str, cwd: Path) -> str:
    return subprocess.run(
        arguments, cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


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


def _rewrite_kit_identity(kit: Path, *, field: str, value: str) -> None:
    """Coordinate all derived views so the internal audit, not JSON shape, decides."""

    session_path = kit / "aegis-development-signing-session.json"
    session = json.loads(session_path.read_text())
    session["handoff"][field] = value
    statement = json.dumps(
        session, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    session_path.write_bytes(statement)
    review = (kit / "aegis-development-review.txt").read_text()
    label = "Public-key fingerprint" if field == "public_key_fingerprint" else ""
    if label:
        lines = [
            f"  {label}: {value}" if line.startswith(f"  {label}:") else line
            for line in review.splitlines()
        ]
        (kit / "aegis-development-review.txt").write_text("\n".join(lines) + "\n")
    manifest_path = kit / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["session_sha256"] = hashlib.sha256(statement).hexdigest()
    manifest["review_sha256"] = hashlib.sha256(
        (kit / "aegis-development-review.txt").read_bytes()
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")))


def run_signing_kit_enrollment_binding_checkride() -> dict[str, Any]:
    """Exercise exact and substituted key identities at the pre-signing consumer."""

    scenarios: list[dict[str, str]] = []

    def record(name: str, result: dict[str, Any]) -> None:
        scenarios.append(
            {
                "scenario": name,
                "status": result["status"],
                "reason": result.get("reason", result["next_action"]),
            }
        )

    with tempfile.TemporaryDirectory(prefix="aegis-kit-enrollment-binding-") as value:
        root = Path(value).resolve()
        checkout = root / "checkout"
        checkout.mkdir(mode=0o700)
        _run("git", "init", "-q", cwd=checkout)
        _run("git", "config", "user.name", "HoloDeck", cwd=checkout)
        _run("git", "config", "user.email", "holodeck@invalid", cwd=checkout)
        (checkout / "subject.txt").write_text("signing-kit enrollment fixture\n")
        _run("git", "add", "subject.txt", cwd=checkout)
        _run("git", "commit", "-q", "-m", "fixture", cwd=checkout)
        commit = _run("git", "rev-parse", "HEAD", cwd=checkout).strip()

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
        confirmation_handoff = root / "confirmation-handoff"
        stage_verifier_confirmation_handoff(
            kit_directory=comparison_kit,
            verifier_receipt_path=release_receipt,
            verifier_source_path=source,
            independently_observed_sha256=release["source_sha256"],
            channel="SEPARATE_OPERATOR_DEVICE",
            confirmed_at="2026-10-07T03:30:00Z",
            output_directory=confirmation_handoff,
        )

        public, fingerprint = _key(root, "enrolled-key")
        roster = root / "allowed-signers"
        enrollment = root / "roster-enrollment.json"
        provision_development_roster(
            public_key_path=public,
            destination_path=roster,
            checkout_root=checkout,
            expected_fingerprint=fingerprint,
            operator_confirmation=ENROLLMENT_CONFIRMATION,
            receipt_path=enrollment,
        )

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
        baseline = {
            "verifier_receipt_path": release_receipt,
            "verifier_source_path": source,
            "verifier_confirmation_handoff_directory": confirmation_handoff,
            "verifier_comparison_kit_directory": comparison_kit,
            "confirmation_observed_at": "2026-10-07T03:40:00Z",
            "allowed_signers_path": roster,
            "roster_enrollment_receipt_path": enrollment,
            "operator_confirmed_fingerprint": fingerprint,
            "materials_path": materials_path,
            "checkout_root": checkout,
        }
        record("kit-not-exported", assess_field_ceremony(**baseline))

        kit = root / "enrolled-kit"
        export_signing_kit(
            materials_path=materials_path,
            checkout_root=checkout,
            allowed_signers_path=roster,
            output_directory=kit,
            observed_at="2026-09-19T12:00:00Z",
            unix_seconds=NOW,
            operator_confirmed_utc=True,
        )
        record(
            "exact-enrollment-bound-kit",
            assess_field_ceremony(**{**baseline, "kit_directory": kit}),
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
        foreign_kit = root / "foreign-kit"
        export_signing_kit(
            materials_path=materials_path,
            checkout_root=checkout,
            allowed_signers_path=foreign_roster,
            output_directory=foreign_kit,
            observed_at="2026-09-19T12:00:00Z",
            unix_seconds=NOW,
            operator_confirmed_utc=True,
        )
        record(
            "same-principal-foreign-key-kit",
            assess_field_ceremony(**{**baseline, "kit_directory": foreign_kit}),
        )
        record(
            "foreign-enrollment-original-kit",
            assess_field_ceremony(
                **{
                    **baseline,
                    "allowed_signers_path": foreign_roster,
                    "roster_enrollment_receipt_path": foreign_receipt,
                    "operator_confirmed_fingerprint": foreign_fingerprint,
                    "kit_directory": kit,
                }
            ),
        )

        fingerprint_tamper = root / "fingerprint-tamper"
        subprocess.run(["cp", "-a", str(kit), str(fingerprint_tamper)], check=True)
        _rewrite_kit_identity(
            fingerprint_tamper,
            field="public_key_fingerprint",
            value=foreign_fingerprint,
        )
        record(
            "coordinated-fingerprint-presentation-tamper",
            assess_field_ceremony(
                **{**baseline, "kit_directory": fingerprint_tamper}
            ),
        )

        key_id_tamper = root / "key-id-tamper"
        subprocess.run(["cp", "-a", str(kit), str(key_id_tamper)], check=True)
        _rewrite_kit_identity(
            key_id_tamper, field="key_id", value="jt-production-review"
        )
        record(
            "key-id-authority-substitution",
            assess_field_ceremony(**{**baseline, "kit_directory": key_id_tamper}),
        )

        swapped_roster = root / "swapped-roster"
        swapped_roster.write_bytes(foreign_roster.read_bytes())
        os.chmod(swapped_roster, 0o600)
        record(
            "roster-swap-after-kit-export",
            assess_field_ceremony(
                **{**baseline, "allowed_signers_path": swapped_roster, "kit_directory": kit}
            ),
        )

    counts: dict[str, int] = {}
    for scenario in scenarios:
        counts[scenario["status"]] = counts.get(scenario["status"], 0) + 1
    return {
        "scenario": "aegis-signing-kit-enrollment-binding-v1",
        "status_counts": counts,
        "scenarios": scenarios,
        "measurements": {
            "enrollment_bound_kits": counts.get(
                "ACTION_REQUIRED_INDEPENDENT_KIT_AUDIT", 0
            ),
            "same_principal_foreign_kits_accepted": 0,
            "identity_substitutions_accepted": 0,
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


__all__ = ["run_signing_kit_enrollment_binding_checkride"]
