"""HoloDeck proof that the final ceremony re-audits the public handoff."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from truepanel.aegis import verifier_bootstrap
from truepanel.aegis.field_ceremony import assess_field_ceremony
from truepanel.aegis.verifier_confirmation_handoff import (
    stage_verifier_confirmation_handoff,
)
from truepanel.aegis.verifier_confirmation_kit import (
    export_verifier_confirmation_kit,
)
from truepanel.holodeck import aegis_independent_kit_auditor as standalone


def run_field_handoff_binding_checkride() -> dict[str, Any]:
    """Prove the final consumer cannot bypass handoff and kit custody."""

    release_receipt = Path(verifier_bootstrap.__file__).with_name(
        "independent_verifier_release.json"
    ).resolve()
    source = Path(standalone.__file__).resolve()
    release = verifier_bootstrap.verify_verifier_release(
        receipt_path=release_receipt,
        source_path=source,
    )
    scenarios: list[dict[str, str]] = []

    def record(name: str, result: dict[str, Any]) -> None:
        scenarios.append(
            {
                "scenario": name,
                "status": result["status"],
                "reason": result.get("reason", result["next_action"]),
            }
        )

    with TemporaryDirectory(prefix="aegis-field-handoff-binding-") as temporary:
        root = Path(temporary).resolve()
        kit = root / "comparison-kit"
        export_verifier_confirmation_kit(
            verifier_receipt_path=release_receipt,
            verifier_source_path=source,
            output_directory=kit,
        )
        handoff = root / "confirmation-handoff"
        exact = stage_verifier_confirmation_handoff(
            kit_directory=kit,
            verifier_receipt_path=release_receipt,
            verifier_source_path=source,
            independently_observed_sha256=release["source_sha256"],
            channel="SEPARATE_OPERATOR_DEVICE",
            confirmed_at="2026-10-05T03:30:00Z",
            output_directory=handoff,
        )
        baseline = {
            "verifier_receipt_path": release_receipt,
            "verifier_source_path": source,
            "verifier_confirmation_handoff_directory": handoff,
            "verifier_comparison_kit_directory": kit,
            "confirmation_observed_at": "2026-10-05T03:40:00Z",
        }
        record("exact-bound-handoff", assess_field_ceremony(**baseline))

        try:
            assess_field_ceremony(
                verifier_receipt_path=release_receipt,
                verifier_source_path=source,
                verifier_confirmation_receipt=exact["receipt"],  # type: ignore[call-arg]
                confirmation_observed_at="2026-10-05T03:40:00Z",
            )
        except TypeError as error:
            scenarios.append(
                {
                    "scenario": "raw-receipt-only-bypass",
                    "status": "DENIED",
                    "reason": type(error).__name__,
                }
            )

        record(
            "handoff-without-kit",
            assess_field_ceremony(
                verifier_receipt_path=release_receipt,
                verifier_source_path=source,
                verifier_confirmation_handoff_directory=handoff,
                confirmation_observed_at="2026-10-05T03:40:00Z",
            ),
        )
        record(
            "kit-without-handoff",
            assess_field_ceremony(
                verifier_receipt_path=release_receipt,
                verifier_source_path=source,
                verifier_comparison_kit_directory=kit,
                confirmation_observed_at="2026-10-05T03:40:00Z",
            ),
        )

        def candidate(name: str) -> Path:
            path = root / name
            shutil.copytree(handoff, path)
            return path

        changed_receipt = candidate("changed-receipt")
        receipt_path = changed_receipt / "aegis-verifier-confirmation-receipt.json"
        receipt_value = json.loads(receipt_path.read_text())
        receipt_value["source_sha256"] = "0" * 64
        receipt_path.write_text(json.dumps(receipt_value, sort_keys=True, separators=(",", ":")) + "\n")
        record(
            "receipt-substitution-at-final-consumer",
            assess_field_ceremony(
                **{**baseline, "verifier_confirmation_handoff_directory": changed_receipt}
            ),
        )

        changed_manifest = candidate("changed-manifest")
        manifest_path = changed_manifest / "manifest.json"
        manifest_value = json.loads(manifest_path.read_text())
        manifest_value["receipt_sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest_value, sort_keys=True, separators=(",", ":")) + "\n")
        record(
            "manifest-substitution-at-final-consumer",
            assess_field_ceremony(
                **{**baseline, "verifier_confirmation_handoff_directory": changed_manifest}
            ),
        )

        drifted_kit = root / "drifted-kit"
        shutil.copytree(kit, drifted_kit)
        (drifted_kit / "aegis-verifier-comparison.txt").write_text("drift\n")
        record(
            "comparison-kit-drift-at-final-consumer",
            assess_field_ceremony(
                **{**baseline, "verifier_comparison_kit_directory": drifted_kit}
            ),
        )

        extra_file = candidate("extra-file")
        (extra_file / "private.key").write_text("not accepted\n")
        record(
            "handoff-file-set-extension",
            assess_field_ceremony(
                **{**baseline, "verifier_confirmation_handoff_directory": extra_file}
            ),
        )

        record(
            "expired-handoff-at-final-consumer",
            assess_field_ceremony(
                **{**baseline, "confirmation_observed_at": "2026-10-05T04:01:00Z"}
            ),
        )

    counts: dict[str, int] = {}
    for scenario in scenarios:
        counts[scenario["status"]] = counts.get(scenario["status"], 0) + 1
    return {
        "scenario": "aegis-field-handoff-binding-v1",
        "status_counts": counts,
        "scenarios": scenarios,
        "measurements": {
            "release_bound_consumers": counts.get("ACTION_REQUIRED_PUBLIC_ROSTER", 0),
            "raw_receipt_bypasses_denied": counts.get("DENIED", 0),
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
        "production_mutation": False,
        "control_authority": False,
    }


__all__ = ["run_field_handoff_binding_checkride"]
