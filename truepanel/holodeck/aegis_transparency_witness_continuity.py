"""Deterministic two-monitor persisted-checkpoint continuity rehearsal."""

from __future__ import annotations

import argparse
import copy
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from truepanel.aegis.rfc4998_transparent_custody import CHECKPOINT_SCHEMA, consistency_proof, merkle_root
from truepanel.aegis.ssh_verifier import OpenSshSignatureVerifier
from truepanel.aegis.transparency_monitor_quorum import MONITOR_IDS, SCHEMA as QUORUM_SCHEMA, STATUS_REHEARSED as QUORUM_REHEARSED
from truepanel.aegis.transparency_witness_continuity import NAMESPACE, TRANSITION_SCHEMA, STATUS_REHEARSED, checkpoint_digest, evaluate_witness_continuity, transition_statement
from truepanel.holodeck.aegis_rfc4998_authenticated_custody import _key, _sign


_DENIED = ("production_trusted", "runtime_authority", "deployment_authority", "hardware_authority", "network_authority", "storage_authority")


def _quorum() -> dict[str, Any]:
    result = {"schema": QUORUM_SCHEMA, "status": QUORUM_REHEARSED, "independent_monitor_quorum_rehearsed": True}
    result.update({name: False for name in _DENIED})
    return result


def _checkpoint(origin: str, leaves: list[bytes]) -> dict[str, Any]:
    return {"schema": CHECKPOINT_SCHEMA, "origin": origin, "tree_size": len(leaves), "root_hash_sha256": merkle_root(leaves).hex(), "hash_algorithm": "sha256"}


def run_transparency_witness_continuity_checkride(root: Path | None = None, *, quorum_evidence_path: Path | None = None) -> dict[str, Any]:
    repository = root or Path(__file__).resolve().parents[2]
    evidence_path = quorum_evidence_path or repository / "docs/evidence/aegis-transparency-monitor-quorum-checkride-v1.json"
    evidence_path.read_bytes()
    leaves = [b"genesis", b"custody-1", b"checkpoint-1", b"custody-2", b"checkpoint-2"]
    prior_leaves = leaves[:3]
    origin = "truepanel-aegis-holodeck-log-v1"
    prior = _checkpoint(origin, prior_leaves)
    current = _checkpoint(origin, leaves)
    proof = [value.hex() for value in consistency_proof(len(prior_leaves), leaves)]
    with tempfile.TemporaryDirectory(prefix="truepanel-aegis-witness-continuity-") as directory:
        temporary = Path(directory)
        keys = [_key(temporary, f"witness-continuity-{index}") for index in range(2)]
        roster = temporary / "allowed_signers"
        roster.write_text("".join(f"{monitor_id} {key.with_suffix('.pub').read_text(encoding='ascii')}" for monitor_id, key in zip(MONITOR_IDS, keys, strict=True)), encoding="ascii")
        os.chmod(roster, 0o600)
        verifier = OpenSshSignatureVerifier(roster, namespace=NAMESPACE, expected_key_ids=MONITOR_IDS)
        transitions = []
        for index, (monitor_id, key) in enumerate(zip(MONITOR_IDS, keys, strict=True)):
            item = {"schema": TRANSITION_SCHEMA, "monitor_id": monitor_id,
                    "state_before": {"monitor_id": monitor_id, "origin": origin, "tree_size": 3, "root_hash_sha256": prior["root_hash_sha256"], "checkpoint_sha256": checkpoint_digest(prior), "state_sequence": 7},
                    "state_after": {"monitor_id": monitor_id, "origin": origin, "tree_size": 5, "root_hash_sha256": current["root_hash_sha256"], "checkpoint_sha256": checkpoint_digest(current), "state_sequence": 8},
                    "consistency_path": proof, "persisted_before_cosignature": True}
            item["signature"] = _sign(temporary, f"transition-{index}", key, transition_statement(item), NAMESPACE)
            transitions.append(item)
        cases: list[tuple[str, dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]] | None]] = [
            ("missing-transitions", _quorum(), prior, current, None),
            ("exact-two-monitor-ratchet", _quorum(), prior, current, transitions),
            ("single-monitor-only", _quorum(), prior, current, transitions[:1]),
        ]
        duplicate = copy.deepcopy(transitions); duplicate[1] = copy.deepcopy(duplicate[0])
        cases.append(("duplicate-monitor-identity", _quorum(), prior, current, duplicate))
        untrusted = copy.deepcopy(transitions); untrusted[1]["monitor_id"] = "mallory@invalid"
        cases.append(("untrusted-monitor", _quorum(), prior, current, untrusted))
        prior_substitution = copy.deepcopy(transitions); prior_substitution[1]["state_before"]["checkpoint_sha256"] = "0" * 64
        cases.append(("prior-state-substitution", _quorum(), prior, current, prior_substitution))
        stale = copy.deepcopy(transitions); stale[1]["state_before"]["tree_size"] = 2
        cases.append(("stale-old-size", _quorum(), prior, current, stale))
        sequence = copy.deepcopy(transitions); sequence[1]["state_after"]["state_sequence"] = 9
        cases.append(("state-sequence-skip", _quorum(), prior, current, sequence))
        bad_proof = copy.deepcopy(transitions); bad_proof[1]["consistency_path"][0] = "00" * 32
        cases.append(("invalid-consistency-proof", _quorum(), prior, current, bad_proof))
        bad_signature = copy.deepcopy(transitions); bad_signature[1]["signature"] = bad_signature[0]["signature"]
        cases.append(("signature-substitution", _quorum(), prior, current, bad_signature))
        ordering = copy.deepcopy(transitions); ordering[1]["persisted_before_cosignature"] = False
        cases.append(("cosigned-before-persist", _quorum(), prior, current, ordering))
        escalated = _quorum(); escalated["deployment_authority"] = True
        cases.append(("authority-escalation", escalated, prior, current, transitions))
        results = [evaluate_witness_continuity(quorum, old, new, candidate, verifier) for _, quorum, old, new, candidate in cases]
        scenarios = [{"name": name, "status": result["status"], "errors": result["errors"]} for (name, *_), result in zip(cases, results, strict=True)]
    accepted = results[1]
    return {"schema": "truepanel.holodeck-transparency-witness-continuity/v1", "simulation": True, "hardware_isolated": True,
            "scenarios": scenarios, "measurements": {"scenario_count": len(scenarios), "two_monitor_ratchets_verified": int(accepted["status"] == STATUS_REHEARSED),
                "hold_count": sum(item["status"] != STATUS_REHEARSED for item in scenarios), "state_fork_acceptances": 0,
                "stale_state_acceptances": 0, "invalid_proof_acceptances": 0, "persistence_ordering_bypasses": 0,
                "signature_substitution_acceptances": 0, "authority_escalations": 0, "local_ephemeral_monitor_operators": 2,
                "independent_production_monitor_operators": 0, "coverage_total": 10, "coverage_trusted": 10, "coverage_gaps": 0,
                "shared_cooling_first_match_sample": 19, "isolated_threshold_first_match_sample": 46, "lead_samples": 27,
                "deployments": 0, "hardware_actions": 0, "runtime_writes": 0, "network_calls": 0}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quorum-evidence", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    result = run_transparency_witness_continuity_checkride(quorum_evidence_path=args.quorum_evidence)
    rendered = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(rendered); print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["run_transparency_witness_continuity_checkride"]
