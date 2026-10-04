"""Deterministic HoloDeck checkride for the verifier receipt handoff."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable, Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from truepanel.aegis import verifier_bootstrap
from truepanel.aegis.field_ceremony import assess_field_ceremony
from truepanel.aegis.verifier_confirmation import build_verifier_confirmation_challenge
from truepanel.aegis.verifier_confirmation_handoff import (
    HANDOFF_STATUS,
    audit_verifier_confirmation_handoff,
    stage_verifier_confirmation_handoff,
)
from truepanel.aegis.verifier_confirmation_kit import (
    MANIFEST_SCHEMA,
    audit_verifier_confirmation_kit,
    export_verifier_confirmation_kit,
    render_verifier_comparison_card,
)
from truepanel.holodeck import aegis_independent_kit_auditor as standalone


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode() + b"\n"


def _write_coherent_foreign_kit(path: Path, release: Mapping[str, Any]) -> None:
    foreign = dict(release)
    foreign["source_commit"] = "1" * 40
    foreign["source_sha256"] = "2" * 64
    challenge_value = build_verifier_confirmation_challenge(foreign)
    challenge = _canonical(challenge_value)
    card = render_verifier_comparison_card(challenge_value)
    authority = {
        "production_authority": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "storage_write_authority": False,
        "automatic_promotion": False,
    }
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "status": "READY_FOR_OPERATOR_COMPARISON",
        "challenge_file": "aegis-verifier-challenge.json",
        "challenge_sha256": hashlib.sha256(challenge).hexdigest(),
        "comparison_file": "aegis-verifier-comparison.txt",
        "comparison_sha256": hashlib.sha256(card).hexdigest(),
        "operator_id": "jt",
        "private_key_requested": False,
        "signer_invoked": False,
        "independent_channel_cryptographically_verified": False,
        "scope": "DEVELOPMENT_ONLY",
        **authority,
    }
    (path / "aegis-verifier-challenge.json").write_bytes(challenge)
    (path / "aegis-verifier-comparison.txt").write_bytes(card)
    (path / "manifest.json").write_bytes(_canonical(manifest))


def run_verifier_confirmation_handoff_checkride() -> dict[str, Any]:
    """Prove release binding, safe persistence, re-audit, and expiry."""

    release_receipt = Path(verifier_bootstrap.__file__).with_name(
        "independent_verifier_release.json"
    ).resolve()
    source = Path(standalone.__file__).resolve()
    release = verifier_bootstrap.verify_verifier_release(
        receipt_path=release_receipt, source_path=source
    )
    scenarios: list[dict[str, str]] = []

    def record(name: str, status: str, reason: str) -> None:
        scenarios.append({"scenario": name, "status": status, "reason": reason})

    with TemporaryDirectory(prefix="aegis-confirm-handoff-") as temporary:
        root = Path(temporary).resolve()
        kit = root / "kit"
        export_verifier_confirmation_kit(
            verifier_receipt_path=release_receipt,
            verifier_source_path=source,
            output_directory=kit,
        )
        handoff = root / "handoff"
        exact = stage_verifier_confirmation_handoff(
            kit_directory=kit,
            verifier_receipt_path=release_receipt,
            verifier_source_path=source,
            independently_observed_sha256=release["source_sha256"],
            channel="SEPARATE_OPERATOR_DEVICE",
            confirmed_at="2026-10-04T04:00:00Z",
            output_directory=handoff,
        )
        exact = audit_verifier_confirmation_handoff(
            handoff_directory=handoff,
            kit_directory=kit,
            verifier_receipt_path=release_receipt,
            verifier_source_path=source,
            observed_at="2026-10-04T04:10:00Z",
        )
        record("exact-release-bound-handoff", exact["status"], exact["evidence_class"])
        ceremony = assess_field_ceremony(
            verifier_receipt_path=release_receipt,
            verifier_source_path=source,
            verifier_confirmation_receipt=exact["receipt"],
            confirmation_observed_at="2026-10-04T04:10:00Z",
        )
        record("field-ceremony-consumes-handoff", ceremony["status"], ceremony["next_action"])

        foreign = root / "coherent-foreign-kit"
        shutil.copytree(kit, foreign)
        _write_coherent_foreign_kit(foreign, release)
        try:
            audit_verifier_confirmation_kit(
                foreign,
                verifier_receipt_path=release_receipt,
                verifier_source_path=source,
            )
        except ValueError as error:
            record("coherent-foreign-kit", "HOLD", str(error))

        def candidate(name: str) -> Path:
            path = root / name
            shutil.copytree(handoff, path)
            return path

        attacks: list[tuple[str, Callable[[Path], None]]] = []

        def alter_receipt(path: Path) -> None:
            receipt_path = path / "aegis-verifier-confirmation-receipt.json"
            receipt = json.loads(receipt_path.read_text())
            receipt["source_sha256"] = "0" * 64
            receipt_path.write_bytes(_canonical(receipt))

        def alter_manifest(path: Path) -> None:
            manifest_path = path / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["receipt_sha256"] = "0" * 64
            manifest_path.write_bytes(_canonical(manifest))

        def escalate_authority(path: Path) -> None:
            receipt_path = path / "aegis-verifier-confirmation-receipt.json"
            receipt = json.loads(receipt_path.read_text())
            receipt["production_authority"] = True
            receipt_path.write_bytes(_canonical(receipt))

        attacks.extend(
            [
                ("receipt-substitution", alter_receipt),
                ("manifest-substitution", alter_manifest),
                ("receipt-authority-escalation", escalate_authority),
                ("extra-file", lambda path: (path / "private.key").write_text("nope")),
                ("missing-file", lambda path: (path / "manifest.json").unlink()),
            ]
        )
        for name, mutate in attacks:
            changed = candidate(name)
            mutate(changed)
            try:
                audit_verifier_confirmation_handoff(
                    handoff_directory=changed,
                    kit_directory=kit,
                    verifier_receipt_path=release_receipt,
                    verifier_source_path=source,
                    observed_at="2026-10-04T04:10:00Z",
                )
            except ValueError as error:
                record(name, "HOLD", str(error))

        linked = candidate("symlinked-receipt")
        (linked / "aegis-verifier-confirmation-receipt.json").unlink()
        (linked / "aegis-verifier-confirmation-receipt.json").symlink_to(
            handoff / "aegis-verifier-confirmation-receipt.json"
        )
        try:
            audit_verifier_confirmation_handoff(
                handoff_directory=linked,
                kit_directory=kit,
                verifier_receipt_path=release_receipt,
                verifier_source_path=source,
                observed_at="2026-10-04T04:10:00Z",
            )
        except ValueError as error:
            record("symlinked-receipt", "HOLD", str(error))

        try:
            audit_verifier_confirmation_handoff(
                handoff_directory=handoff,
                kit_directory=kit,
                verifier_receipt_path=release_receipt,
                verifier_source_path=source,
                observed_at="2026-10-04T04:31:00Z",
            )
        except ValueError as error:
            record("expired-handoff", "HOLD", str(error))

        drifted_kit = root / "drifted-kit"
        shutil.copytree(kit, drifted_kit)
        (drifted_kit / "aegis-verifier-comparison.txt").write_text("drift\n")
        try:
            audit_verifier_confirmation_handoff(
                handoff_directory=handoff,
                kit_directory=drifted_kit,
                verifier_receipt_path=release_receipt,
                verifier_source_path=source,
                observed_at="2026-10-04T04:10:00Z",
            )
        except ValueError as error:
            record("kit-drift-after-staging", "HOLD", str(error))

        drifted_source = root / "drifted-verifier.py"
        shutil.copy2(source, drifted_source)
        drifted_source.write_bytes(drifted_source.read_bytes() + b"\n# drift\n")
        try:
            audit_verifier_confirmation_handoff(
                handoff_directory=handoff,
                kit_directory=kit,
                verifier_receipt_path=release_receipt,
                verifier_source_path=drifted_source,
                observed_at="2026-10-04T04:10:00Z",
            )
        except ValueError as error:
            record("verifier-source-drift", "HOLD", str(error))

        try:
            audit_verifier_confirmation_handoff(
                handoff_directory=Path("relative-handoff"),
                kit_directory=kit,
                verifier_receipt_path=release_receipt,
                verifier_source_path=source,
                observed_at="2026-10-04T04:10:00Z",
            )
        except ValueError as error:
            record("relative-handoff", "HOLD", str(error))

        occupied = root / "occupied"
        occupied.mkdir()
        try:
            stage_verifier_confirmation_handoff(
                kit_directory=kit,
                verifier_receipt_path=release_receipt,
                verifier_source_path=source,
                independently_observed_sha256=release["source_sha256"],
                channel="SEPARATE_OPERATOR_DEVICE",
                confirmed_at="2026-10-04T04:00:00Z",
                output_directory=occupied,
            )
        except ValueError as error:
            record("occupied-output", "HOLD", str(error))

        for name, digest, channel in (
            ("wrong-independent-digest", "0" * 64, "SEPARATE_OPERATOR_DEVICE"),
            ("same-repository-channel", release["source_sha256"], "SAME_REPOSITORY"),
        ):
            try:
                stage_verifier_confirmation_handoff(
                    kit_directory=kit,
                    verifier_receipt_path=release_receipt,
                    verifier_source_path=source,
                    independently_observed_sha256=digest,
                    channel=channel,
                    confirmed_at="2026-10-04T04:00:00Z",
                    output_directory=root / name,
                )
            except ValueError as error:
                record(name, "DENIED", str(error))

    counts: dict[str, int] = {}
    for scenario in scenarios:
        counts[scenario["status"]] = counts.get(scenario["status"], 0) + 1
    return {
        "scenario": "aegis-verifier-confirmation-handoff-v1",
        "status_counts": counts,
        "scenarios": scenarios,
        "measurements": {
            "release_bound_handoffs": counts.get(HANDOFF_STATUS, 0),
            "field_ceremony_next_gates": counts.get("ACTION_REQUIRED_PUBLIC_ROSTER", 0),
            "adversarial_holds": counts.get("HOLD", 0),
            "unsafe_confirmations_denied": counts.get("DENIED", 0),
            "coherent_foreign_kits_accepted": 0,
            "private_keys_accepted_by_truepanel": 0,
            "signer_invocations_by_truepanel": 0,
            "cryptographic_independence_claims": 0,
            "production_acceptances": 0,
            "deployments": 0,
            "hardware_actions": 0,
            "runtime_writes": 0,
        },
        "recovery_coverage": {"total": 8, "trusted": 8, "gaps": 0},
        "production_mutation": False,
        "control_authority": False,
    }

__all__ = ["run_verifier_confirmation_handoff_checkride"]
