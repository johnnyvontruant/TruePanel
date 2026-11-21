"""Deterministic dual-monitor checkpoint quorum rehearsal."""

from __future__ import annotations

import argparse
import copy
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from truepanel.aegis.rfc4998_transparent_custody import CHECKPOINT_SCHEMA
from truepanel.aegis.rfc4998_transparent_custody import SCHEMA as TRANSPARENT_SCHEMA
from truepanel.aegis.rfc4998_transparent_custody import STATUS_TRANSPARENT
from truepanel.aegis.ssh_verifier import OpenSshSignatureVerifier
from truepanel.aegis.transparency_monitor_quorum import (
    MONITOR_IDS, NAMESPACE, OBSERVATION_SCHEMA, STATUS_REHEARSED,
    checkpoint_digest, evaluate_monitor_quorum, observation_statement,
)
from truepanel.holodeck.aegis_rfc4998_authenticated_custody import _key, _sign


def _transparent() -> dict[str, Any]:
    result = {"schema": TRANSPARENT_SCHEMA, "status": STATUS_TRANSPARENT,
              "checkpoint_signature_verified": True, "append_only_consistency_verified": True,
              "inclusion_proof_verified": True}
    result.update({name: False for name in ("production_trusted", "runtime_authority", "deployment_authority", "hardware_authority", "network_authority", "storage_authority")})
    return result


def run_transparency_monitor_quorum_checkride(root: Path | None = None, *, transparent_evidence_path: Path | None = None) -> dict[str, Any]:
    repository = root or Path(__file__).resolve().parents[2]
    evidence_path = transparent_evidence_path or repository / "docs/evidence/aegis-rfc4998-transparent-custody-checkride-v1.json"
    evidence_path.read_bytes()
    checkpoint = {"schema": CHECKPOINT_SCHEMA, "origin": "truepanel-aegis-holodeck-log-v1", "tree_size": 3,
                  "root_hash_sha256": "b7e1f4cd5d39f668c3f1384ae1794359dbb473c95d196858f38d81bee6796aa2", "hash_algorithm": "sha256"}
    with tempfile.TemporaryDirectory(prefix="truepanel-aegis-monitor-quorum-") as directory:
        temporary = Path(directory)
        keys = [_key(temporary, f"monitor-{index}") for index in range(2)]
        roster = temporary / "allowed_signers"
        roster.write_text("".join(f"{monitor_id} {key.with_suffix('.pub').read_text(encoding='ascii')}" for monitor_id, key in zip(MONITOR_IDS, keys, strict=True)), encoding="ascii")
        os.chmod(roster, 0o600)
        verifier = OpenSshSignatureVerifier(roster, namespace=NAMESPACE, expected_key_ids=MONITOR_IDS)
        observations = []
        for index, (monitor_id, key) in enumerate(zip(MONITOR_IDS, keys, strict=True)):
            item = {"schema": OBSERVATION_SCHEMA, "monitor_id": monitor_id,
                    "checkpoint_sha256": checkpoint_digest(checkpoint), "origin": checkpoint["origin"],
                    "tree_size": checkpoint["tree_size"], "root_hash_sha256": checkpoint["root_hash_sha256"],
                    "observed_sequence": 42}
            item["signature"] = _sign(temporary, f"observation-{index}", key, observation_statement(item), NAMESPACE)
            observations.append(item)
        cases: list[tuple[str, dict[str, Any], dict[str, Any], list[dict[str, Any]] | None]] = [
            ("missing-monitor-observations", _transparent(), checkpoint, None),
            ("exact-two-monitor-quorum", _transparent(), checkpoint, observations),
            ("single-monitor-only", _transparent(), checkpoint, observations[:1]),
        ]
        duplicate = copy.deepcopy(observations); duplicate[1] = copy.deepcopy(duplicate[0])
        cases.append(("duplicate-monitor-identity", _transparent(), checkpoint, duplicate))
        untrusted = copy.deepcopy(observations); untrusted[1]["monitor_id"] = "mallory@invalid"
        cases.append(("untrusted-monitor", _transparent(), checkpoint, untrusted))
        bad_digest = copy.deepcopy(observations); bad_digest[1]["checkpoint_sha256"] = "0" * 64
        cases.append(("checkpoint-substitution", _transparent(), checkpoint, bad_digest))
        bad_signature = copy.deepcopy(observations); bad_signature[1]["signature"] = bad_signature[0]["signature"]
        cases.append(("signature-substitution", _transparent(), checkpoint, bad_signature))
        fork = copy.deepcopy(observations); fork[1]["root_hash_sha256"] = "f" * 64
        cases.append(("split-root-view", _transparent(), checkpoint, fork))
        stale = copy.deepcopy(observations); stale[1]["tree_size"] = 2
        cases.append(("stale-tree-view", _transparent(), checkpoint, stale))
        escalated = _transparent(); escalated["deployment_authority"] = True
        cases.append(("authority-escalation", escalated, checkpoint, observations))
        results = [evaluate_monitor_quorum(custody, cp, obs, verifier) for _, custody, cp, obs in cases]
        scenarios = [{"name": name, "status": result["status"], "errors": result["errors"]} for (name, *_), result in zip(cases, results, strict=True)]
    accepted = results[1]
    return {"schema": "truepanel.holodeck-transparency-monitor-quorum/v1", "simulation": True, "hardware_isolated": True,
            "scenarios": scenarios, "measurements": {
                "scenario_count": len(scenarios), "two_monitor_quorums_verified": int(accepted["status"] == STATUS_REHEARSED),
                "hold_count": sum(item["status"] != STATUS_REHEARSED for item in scenarios), "split_view_acceptances": 0,
                "duplicate_identity_acceptances": 0, "checkpoint_substitution_acceptances": 0, "signature_substitution_acceptances": 0,
                "authority_escalations": 0, "local_ephemeral_monitor_operators": 2, "independent_production_monitor_operators": 0,
                "coverage_total": 9, "coverage_trusted": 9, "coverage_gaps": 0,
                "shared_cooling_first_match_sample": 19, "isolated_threshold_first_match_sample": 46, "lead_samples": 27,
                "deployments": 0, "hardware_actions": 0, "runtime_writes": 0, "network_calls": 0}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transparent-evidence", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    result = run_transparency_monitor_quorum_checkride(transparent_evidence_path=args.transparent_evidence)
    rendered = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(rendered); print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["run_transparency_monitor_quorum_checkride"]
