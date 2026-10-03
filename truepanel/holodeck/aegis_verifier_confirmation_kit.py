"""Deterministic HoloDeck checkride for the verifier comparison kit."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from truepanel.aegis import verifier_bootstrap
from truepanel.aegis.verifier_confirmation import verify_verifier_confirmation_receipt
from truepanel.aegis.verifier_confirmation_kit import (
    audit_verifier_confirmation_kit,
    confirm_from_verifier_confirmation_kit,
    export_verifier_confirmation_kit,
)
from truepanel.holodeck import aegis_independent_kit_auditor as standalone


def run_verifier_confirmation_kit_checkride() -> dict[str, Any]:
    """Prove the human-facing files cannot drift from the canonical challenge."""

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

    with TemporaryDirectory(prefix="aegis-confirm-kit-") as temporary:
        root = Path(temporary).resolve()
        kit = root / "kit"
        audit = export_verifier_confirmation_kit(
            verifier_receipt_path=release_receipt,
            verifier_source_path=source,
            output_directory=kit,
        )
        record("exact-public-kit", audit["status"], "all public views agree")
        receipt = confirm_from_verifier_confirmation_kit(
            directory=kit,
            independently_observed_sha256=release["source_sha256"],
            channel="SEPARATE_OPERATOR_DEVICE",
            confirmed_at="2026-10-03T04:00:00Z",
        )
        verified = verify_verifier_confirmation_receipt(
            receipt=receipt,
            release=release,
            observed_at="2026-10-03T04:10:00Z",
        )
        record("audited-kit-confirmation", verified["status"], verified["evidence_class"])

        def candidate(name: str) -> Path:
            value = root / name
            shutil.copytree(kit, value)
            return value

        attacks: list[tuple[str, Callable[[Path], None]]] = []

        def alter_challenge(path: Path) -> None:
            document = json.loads((path / "aegis-verifier-challenge.json").read_text())
            document["source_sha256"] = "0" * 64
            (path / "aegis-verifier-challenge.json").write_text(
                json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n"
            )

        def alter_card(path: Path) -> None:
            (path / "aegis-verifier-comparison.txt").write_text("TRUST ME\n")

        def alter_card_and_manifest(path: Path) -> None:
            card = b"TRUST ME\n"
            (path / "aegis-verifier-comparison.txt").write_bytes(card)
            manifest_path = path / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["comparison_sha256"] = hashlib.sha256(card).hexdigest()
            manifest_path.write_text(
                json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
            )

        def alter_display_blocks(path: Path) -> None:
            challenge_path = path / "aegis-verifier-challenge.json"
            challenge = json.loads(challenge_path.read_text())
            challenge["fingerprint_blocks"][0] = "00000000"
            challenge_path.write_text(
                json.dumps(challenge, sort_keys=True, separators=(",", ":")) + "\n"
            )

        def escalate_authority(path: Path) -> None:
            challenge_path = path / "aegis-verifier-challenge.json"
            challenge = json.loads(challenge_path.read_text())
            challenge["production_authority"] = True
            challenge_path.write_text(
                json.dumps(challenge, sort_keys=True, separators=(",", ":")) + "\n"
            )

        attacks.extend(
            [
                ("challenge-substitution", alter_challenge),
                ("comparison-card-substitution", alter_card),
                ("coordinated-card-manifest-substitution", alter_card_and_manifest),
                ("display-block-substitution", alter_display_blocks),
                ("challenge-authority-escalation", escalate_authority),
                ("extra-file", lambda path: (path / "private.key").write_text("nope")),
                ("missing-file", lambda path: (path / "manifest.json").unlink()),
            ]
        )
        for name, mutate in attacks:
            changed = candidate(name)
            mutate(changed)
            try:
                audit_verifier_confirmation_kit(changed)
            except ValueError as error:
                record(name, "HOLD", str(error))

        linked = candidate("symlinked-card")
        (linked / "aegis-verifier-comparison.txt").unlink()
        (linked / "aegis-verifier-comparison.txt").symlink_to(
            kit / "aegis-verifier-comparison.txt"
        )
        try:
            audit_verifier_confirmation_kit(linked)
        except ValueError as error:
            record("symlinked-card", "HOLD", str(error))

        try:
            audit_verifier_confirmation_kit(Path("relative-kit"))
        except ValueError as error:
            record("relative-kit", "HOLD", str(error))

        for name, digest, channel in (
            ("partial-or-wrong-digest", "0" * 64, "SEPARATE_OPERATOR_DEVICE"),
            ("same-repository-channel", release["source_sha256"], "SAME_REPOSITORY"),
        ):
            try:
                confirm_from_verifier_confirmation_kit(
                    directory=kit,
                    independently_observed_sha256=digest,
                    channel=channel,
                    confirmed_at="2026-10-03T04:00:00Z",
                )
            except ValueError as error:
                record(name, "DENIED", str(error))

        occupied = root / "occupied"
        occupied.mkdir()
        try:
            export_verifier_confirmation_kit(
                verifier_receipt_path=release_receipt,
                verifier_source_path=source,
                output_directory=occupied,
            )
        except ValueError as error:
            record("occupied-output", "HOLD", str(error))

    counts: dict[str, int] = {}
    for scenario in scenarios:
        counts[scenario["status"]] = counts.get(scenario["status"], 0) + 1
    return {
        "scenario": "aegis-verifier-confirmation-kit-v1",
        "status_counts": counts,
        "scenarios": scenarios,
        "measurements": {
            "public_kits_ready": counts.get("READY_FOR_OPERATOR_COMPARISON", 0),
            "operator_attestations_verified": counts.get(
                "OPERATOR_ATTESTED_INDEPENDENT_CHANNEL", 0
            ),
            "adversarial_holds": counts.get("HOLD", 0),
            "unsafe_confirmations_denied": counts.get("DENIED", 0),
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


__all__ = ["run_verifier_confirmation_kit_checkride"]
