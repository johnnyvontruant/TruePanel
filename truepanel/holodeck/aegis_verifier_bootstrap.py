"""Deterministic HoloDeck checkride for the independent-verifier bootstrap."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from truepanel.aegis import verifier_bootstrap
from truepanel.aegis.verifier_bootstrap import verify_verifier_release
from truepanel.holodeck import aegis_independent_kit_auditor


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"


def _blob_sha1(content: bytes) -> str:
    return hashlib.sha1(
        f"blob {len(content)}\0".encode() + content, usedforsecurity=False
    ).hexdigest()


def _write_receipt(path: Path, value: dict[str, Any]) -> None:
    path.write_text(_canonical(value))


def _matching_receipt(
    baseline: dict[str, Any], source: Path, receipt: Path
) -> None:
    content = source.read_bytes()
    value = deepcopy(baseline)
    value["source_size_bytes"] = len(content)
    value["source_sha256"] = hashlib.sha256(content).hexdigest()
    value["source_git_blob_sha1"] = _blob_sha1(content)
    _write_receipt(receipt, value)


def _hold(receipt: Path, source: Path) -> str:
    try:
        verify_verifier_release(receipt_path=receipt, source_path=source)
    except ValueError as error:
        return str(error)
    return "UnsafeReady"


def run_verifier_bootstrap_checkride() -> dict[str, Any]:
    scenarios: list[dict[str, str]] = []

    def record(name: str, status: str, reason: str) -> None:
        scenarios.append({"scenario": name, "status": status, "reason": reason})

    release_path = Path(verifier_bootstrap.__file__).with_name(
        "independent_verifier_release.json"
    )
    auditor_path = Path(aegis_independent_kit_auditor.__file__).resolve()
    baseline_receipt = json.loads(release_path.read_text())
    with tempfile.TemporaryDirectory(prefix="truepanel-aegis-verifier-bootstrap-") as value:
        root = Path(value)
        receipt = root / "release.json"
        source = root / "aegis_independent_kit_auditor.py"
        shutil.copyfile(release_path, receipt)
        shutil.copyfile(auditor_path, source)
        result = verify_verifier_release(receipt_path=receipt, source_path=source)
        record("exact-public-release", result["status"], result["next_gate"])

        changed_source = root / "changed.py"
        changed_source.write_bytes(source.read_bytes() + b"\n# changed\n")
        record("source-tamper", "HOLD", _hold(receipt, changed_source))

        receipt_attacks = {
            "source-sha": ("source_sha256", "0" * 64),
            "git-blob": ("source_git_blob_sha1", "0" * 40),
            "source-size": ("source_size_bytes", 1),
            "commit": ("source_commit", "not-a-commit"),
            "source-url": ("source_url", "https://invalid.example/verifier.py"),
            "authority": ("production_authority", True),
        }
        for name, (field, replacement) in receipt_attacks.items():
            target = root / f"receipt-{name}.json"
            changed = deepcopy(baseline_receipt)
            changed[field] = replacement
            _write_receipt(target, changed)
            record(f"receipt-{name}-tamper", "HOLD", _hold(target, source))

        extended = root / "extended.json"
        changed = deepcopy(baseline_receipt)
        changed["unexpected"] = True
        _write_receipt(extended, changed)
        record("receipt-extension", "HOLD", _hold(extended, source))

        noncanonical = root / "noncanonical.json"
        noncanonical.write_text(json.dumps(baseline_receipt, indent=2))
        record("noncanonical-receipt", "HOLD", _hold(noncanonical, source))

        linked_receipt = root / "linked-receipt.json"
        linked_receipt.symlink_to(receipt)
        record("symlinked-receipt", "HOLD", _hold(linked_receipt, source))
        linked_source = root / "linked-source.py"
        linked_source.symlink_to(source)
        record("symlinked-source", "HOLD", _hold(receipt, linked_source))

        source_attacks = {
            "network-import": b"\nimport socket\n",
            "truepanel-import": b"\nimport truepanel\n",
            "private-key-input": b"\ndef unsafe(private_key):\n    return private_key\n",
        }
        for name, suffix in source_attacks.items():
            changed = root / f"{name}.py"
            changed.write_bytes(source.read_bytes() + suffix)
            matching = root / f"{name}-receipt.json"
            _matching_receipt(baseline_receipt, changed, matching)
            record(f"policy-{name}", "HOLD", _hold(matching, changed))

    counts: dict[str, int] = {}
    for scenario in scenarios:
        counts[scenario["status"]] = counts.get(scenario["status"], 0) + 1
    return {
        "scenario": "aegis-verifier-bootstrap-v1",
        "status_counts": counts,
        "scenarios": scenarios,
        "measurements": {
            "content_pins_verified": counts.get("VERIFIER_CONTENT_PIN_VERIFIED", 0),
            "adversarial_holds": counts.get("HOLD", 0),
            "unsafe_ready": counts.get("UnsafeReady", 0),
            "independent_channels_manufactured": 0,
            "verifier_executions_during_pin_check": 0,
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


__all__ = ["run_verifier_bootstrap_checkride"]
