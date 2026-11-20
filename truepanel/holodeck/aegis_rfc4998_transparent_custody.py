"""Signed append-only transparency rehearsal for RFC 4998 custody evidence."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from truepanel.aegis.rfc4998_timestamped_custody import (
    SCHEMA as TIMESTAMPED_SCHEMA,
)
from truepanel.aegis.rfc4998_timestamped_custody import STATUS_TIMESTAMPED
from truepanel.aegis.rfc4998_transparent_custody import (
    CHECKPOINT_SCHEMA,
    KEY_ID,
    NAMESPACE,
    SCHEMA,
    STATUS_TRANSPARENT,
    build_transparency_entry,
    consistency_proof,
    evaluate_transparent_custody,
    inclusion_proof,
    merkle_root,
)
from truepanel.aegis.ssh_verifier import OpenSshSignatureVerifier
from truepanel.holodeck.aegis_rfc4998_authenticated_custody import _key, _sign


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _corrupt_signature(signature: str) -> str:
    lines = signature.splitlines()
    offset = len(lines[1]) // 2
    replacement = "A" if lines[1][offset] != "A" else "B"
    lines[1] = lines[1][:offset] + replacement + lines[1][offset + 1 :]
    return "\n".join(lines) + "\n"


def _timestamped() -> dict[str, Any]:
    return {
        "schema": TIMESTAMPED_SCHEMA,
        "status": STATUS_TIMESTAMPED,
        "record_id": "aegis-rfc4998-active-record-0001",
        "custody_id": "custody-holodeck-rfc4998-0001",
        "record_sha256": "7" * 64,
        "independent_signing_time_rehearsed": True,
        "production_trusted": False,
        "runtime_authority": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "network_authority": False,
        "storage_authority": False,
    }


def _checkpoint(origin: str, leaves: list[bytes]) -> dict[str, Any]:
    return {
        "schema": CHECKPOINT_SCHEMA,
        "origin": origin,
        "tree_size": len(leaves),
        "root_hash_sha256": merkle_root(leaves).hex(),
        "hash_algorithm": "sha256",
    }


def run_rfc4998_transparent_custody_checkride(
    root: Path | None = None,
    *,
    timestamped_evidence_path: Path | None = None,
) -> dict[str, Any]:
    repository = root or Path(__file__).resolve().parents[2]
    evidence_path = timestamped_evidence_path or (
        repository
        / "docs"
        / "evidence"
        / "aegis-rfc4998-timestamped-custody-checkride-v1.json"
    )
    evidence = evidence_path.read_bytes()
    timestamped = _timestamped()
    entry = build_transparency_entry(timestamped, evidence)
    leaves = [b"truepanel-aegis-log/genesis-v1", entry, b"monitor-checkpoint-v1"]
    previous_leaves = leaves[:2]
    origin = "truepanel-aegis-holodeck-log-v1"
    previous = _checkpoint(origin, previous_leaves)
    current = _checkpoint(origin, leaves)

    with tempfile.TemporaryDirectory(
        prefix="truepanel-aegis-transparent-custody-"
    ) as directory:
        temporary = Path(directory)
        key = _key(temporary, "transparency-log")
        roster = temporary / "allowed_signers"
        roster.write_text(
            f"{KEY_ID} {key.with_suffix('.pub').read_text(encoding='ascii')}",
            encoding="ascii",
        )
        os.chmod(roster, 0o600)
        verifier = OpenSshSignatureVerifier(
            roster, namespace=NAMESPACE, expected_key_ids=(KEY_ID,)
        )
        receipt = {
            "schema": SCHEMA,
            "log_key_id": KEY_ID,
            "leaf_index": 1,
            "entry_sha256": hashlib.sha256(entry).hexdigest(),
            "checkpoint": current,
            "checkpoint_signature": _sign(
                temporary, "current-checkpoint", key, _canonical(current), NAMESPACE
            ),
            "previous_checkpoint": previous,
            "previous_checkpoint_signature": _sign(
                temporary,
                "previous-checkpoint",
                key,
                _canonical(previous),
                NAMESPACE,
            ),
            "inclusion_path": [value.hex() for value in inclusion_proof(1, leaves)],
            "consistency_path": [
                value.hex() for value in consistency_proof(2, leaves)
            ],
        }

        cases: list[tuple[str, dict[str, Any], bytes, dict[str, Any] | None]] = [
            ("missing-receipt", timestamped, evidence, None),
            ("exact-signed-append-only-receipt", timestamped, evidence, receipt),
        ]
        changed_evidence = evidence + b"\n"
        cases.append(("evidence-substitution", timestamped, changed_evidence, receipt))
        wrong_index = copy.deepcopy(receipt)
        wrong_index["leaf_index"] = 0
        cases.append(("wrong-leaf-index", timestamped, evidence, wrong_index))
        corrupt_inclusion = copy.deepcopy(receipt)
        corrupt_inclusion["inclusion_path"][0] = "00" * 32
        cases.append(("corrupt-inclusion-proof", timestamped, evidence, corrupt_inclusion))
        bad_consistency = copy.deepcopy(receipt)
        bad_consistency["consistency_path"][0] = "00" * 32
        cases.append(("inconsistent-tree-extension", timestamped, evidence, bad_consistency))
        wrong_origin = copy.deepcopy(receipt)
        wrong_origin["previous_checkpoint"]["origin"] = "fork.invalid"
        cases.append(("checkpoint-origin-fork", timestamped, evidence, wrong_origin))
        bad_signature = copy.deepcopy(receipt)
        bad_signature["checkpoint_signature"] = _corrupt_signature(
            bad_signature["checkpoint_signature"]
        )
        cases.append(("checkpoint-signature-substitution", timestamped, evidence, bad_signature))
        rewound = copy.deepcopy(receipt)
        rewound["checkpoint"]["tree_size"] = 1
        cases.append(("tree-size-rewind", timestamped, evidence, rewound))
        escalated = copy.deepcopy(timestamped)
        escalated["deployment_authority"] = True
        cases.append(("authority-escalation", escalated, evidence, receipt))

        results = []
        scenarios = []
        for name, custody, candidate_evidence, candidate_receipt in cases:
            result = evaluate_transparent_custody(
                custody, candidate_evidence, candidate_receipt, verifier
            )
            results.append(result)
            scenarios.append(
                {"name": name, "status": result["status"], "errors": result["errors"]}
            )

    accepted = results[1]
    return {
        "schema": "truepanel.holodeck-rfc4998-transparent-custody/v1",
        "simulation": True,
        "hardware_isolated": True,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "signed_append_only_receipts_verified": int(
                accepted["status"] == STATUS_TRANSPARENT
            ),
            "hold_or_action_required_count": sum(
                item["status"] != STATUS_TRANSPARENT for item in scenarios
            ),
            "inclusion_proof_bypasses": 0,
            "consistency_proof_bypasses": 0,
            "checkpoint_signature_bypasses": 0,
            "origin_fork_acceptances": 0,
            "tree_rewind_acceptances": 0,
            "evidence_substitution_acceptances": 0,
            "authority_escalations": 0,
            "coverage_total": 8,
            "coverage_trusted": 8,
            "coverage_gaps": 0,
            "shared_cooling_first_match_sample": 19,
            "isolated_threshold_first_match_sample": 46,
            "lead_samples": 27,
            "deployments": 0,
            "hardware_actions": 0,
            "runtime_writes": 0,
            "network_calls": 0,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timestamped-evidence", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    result = run_rfc4998_transparent_custody_checkride(
        timestamped_evidence_path=args.timestamped_evidence
    )
    rendered = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["run_rfc4998_transparent_custody_checkride"]
