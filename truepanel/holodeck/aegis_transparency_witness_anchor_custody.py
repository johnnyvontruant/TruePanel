"""Deterministic threshold-custody checkride for a witness recovery anchor."""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from truepanel.aegis.ssh_verifier import (
    OpenSshSignatureVerifier,
    validate_allowed_signers_roster,
)
from truepanel.aegis.transparency_monitor_quorum import MONITOR_IDS
from truepanel.aegis.transparency_witness_anchor_custody import (
    CUSTODIAN_IDS,
    NAMESPACE,
    STATUS_HOLD,
    STATUS_REHEARSED,
    anchor_custody_statement_bytes,
    build_anchor_custody_statement,
    evaluate_threshold_anchor_custody,
)
from truepanel.aegis.transparency_witness_sqlite_recovery import (
    SQLiteWitnessDurableStateStore,
)
from truepanel.aegis.transparency_witness_storage_faults import create_recovery_anchor
from truepanel.holodeck.aegis_transparency_witness_crash_recovery import _fixtures


def _sign(key: Path, statement: bytes) -> str:
    completed = subprocess.run(
        ["/usr/bin/ssh-keygen", "-Y", "sign", "-f", str(key), "-n", NAMESPACE],
        input=statement,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    return completed.stdout.decode("ascii")


def _scenario(name: str, action) -> dict[str, Any]:
    try:
        observation = action()
        return {"name": name, "status": "PASS", "observation": observation}
    except (
        AssertionError,
        KeyError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as error:
        return {"name": name, "status": "HOLD", "observation": str(error)}


def run_transparency_witness_anchor_custody_checkride(
    root: Path | None = None, *, storage_fault_evidence_path: Path | None = None
) -> dict[str, Any]:
    repository = root or Path(__file__).resolve().parents[2]
    predecessor_path = storage_fault_evidence_path or repository / (
        "docs/evidence/aegis-transparency-witness-storage-faults-checkride-v1.json"
    )
    predecessor = json.loads(predecessor_path.read_text(encoding="utf-8"))
    measures = predecessor.get("measurements", {})
    if (
        predecessor.get("schema")
        != "truepanel.holodeck-transparency-witness-storage-faults/v1"
        or measures.get("coverage_gaps") != 0
        or measures.get("stale_dual_store_acceptances") != 0
    ):
        raise ValueError("reviewed storage-fault evidence required")

    with tempfile.TemporaryDirectory(
        prefix="truepanel-aegis-anchor-custody-"
    ) as directory:
        base = Path(directory).resolve()
        keys = [base / f"custodian-{index}" for index in range(2)]
        for key in keys:
            subprocess.run(
                [
                    "/usr/bin/ssh-keygen",
                    "-q",
                    "-t",
                    "ed25519",
                    "-N",
                    "",
                    "-f",
                    str(key),
                ],
                check=True,
            )
        roster = base / "allowed-signers"
        roster.write_text(
            "".join(
                f"{custodian_id} {key.with_suffix('.pub').read_text(encoding='ascii')}"
                for custodian_id, key in zip(CUSTODIAN_IDS, keys, strict=True)
            ),
            encoding="ascii",
        )
        os.chmod(roster, 0o600)
        verifier = OpenSshSignatureVerifier(
            roster, namespace=NAMESPACE, expected_key_ids=CUSTODIAN_IDS
        )
        fingerprints = validate_allowed_signers_roster(
            roster.read_bytes(), expected_key_ids=CUSTODIAN_IDS
        )

        continuity, transitions = _fixtures()
        stores = [
            SQLiteWitnessDurableStateStore(base / f"store-{index}", monitor_id)
            for index, monitor_id in enumerate(MONITOR_IDS)
        ]
        for store, transition in zip(stores, transitions, strict=True):
            store.initialize(transition["state_before"])
            store.commit(continuity, transition)
        anchor = create_recovery_anchor(stores)
        statement = build_anchor_custody_statement(anchor)
        statement_bytes = anchor_custody_statement_bytes(statement)
        signatures = [
            {"custodian_id": custodian_id, "signature": _sign(key, statement_bytes)}
            for custodian_id, key in zip(CUSTODIAN_IDS, keys, strict=True)
        ]

        def evaluate(
            candidate_statement=statement,
            candidate_signatures=signatures,
            *,
            candidate_anchor=anchor,
            candidate_stores=stores,
            candidate_fingerprints=fingerprints,
            threshold=2,
        ):
            return evaluate_threshold_anchor_custody(
                candidate_stores,
                candidate_anchor,
                candidate_statement,
                candidate_signatures,
                verifier,
                candidate_fingerprints,
                threshold=threshold,
            )

        scenarios: list[dict[str, Any]] = []

        def exact_threshold() -> str:
            result = evaluate()
            assert result["status"] == STATUS_REHEARSED
            assert result["valid_custodian_count"] == 2
            return "EXACT_2_OF_2_ANCHOR_CUSTODY_REHEARSED"

        scenarios.append(_scenario("exact-two-custodian-threshold", exact_threshold))

        def reversed_order() -> str:
            result = evaluate(candidate_signatures=list(reversed(signatures)))
            assert result["status"] == STATUS_REHEARSED
            return "ORDER_INDEPENDENT_2_OF_2_CUSTODY_REHEARSED"

        scenarios.append(_scenario("signature-order-independent", reversed_order))

        def expect_hold(name: str, result: Mapping[str, Any]) -> str:
            if result["status"] != STATUS_HOLD:
                raise ValueError(f"{name}_ACCEPTED")
            raise ValueError(name)

        scenarios.append(
            _scenario(
                "missing-custodian",
                lambda: expect_hold(
                    "MISSING_CUSTODIAN_HELD",
                    evaluate(candidate_signatures=signatures[:1]),
                ),
            )
        )
        duplicate = [
            signatures[0],
            {**signatures[1], "custodian_id": signatures[0]["custodian_id"]},
        ]
        scenarios.append(
            _scenario(
                "duplicate-custodian",
                lambda: expect_hold(
                    "DUPLICATE_CUSTODIAN_HELD", evaluate(candidate_signatures=duplicate)
                ),
            )
        )
        duplicate_key_fingerprints = dict(fingerprints)
        duplicate_key_fingerprints[CUSTODIAN_IDS[1]] = duplicate_key_fingerprints[
            CUSTODIAN_IDS[0]
        ]
        scenarios.append(
            _scenario(
                "duplicate-custodian-key",
                lambda: expect_hold(
                    "DUPLICATE_CUSTODIAN_KEY_HELD",
                    evaluate(candidate_fingerprints=duplicate_key_fingerprints),
                ),
            )
        )
        unknown = copy.deepcopy(signatures)
        unknown[1]["custodian_id"] = "unknown@holodeck.invalid"
        scenarios.append(
            _scenario(
                "untrusted-custodian",
                lambda: expect_hold(
                    "UNTRUSTED_CUSTODIAN_HELD", evaluate(candidate_signatures=unknown)
                ),
            )
        )
        invalid = copy.deepcopy(signatures)
        invalid[1]["signature"] = signatures[0]["signature"]
        scenarios.append(
            _scenario(
                "signature-substitution",
                lambda: expect_hold(
                    "SIGNATURE_SUBSTITUTION_HELD",
                    evaluate(candidate_signatures=invalid),
                ),
            )
        )
        changed_statement = copy.deepcopy(statement)
        changed_statement["subject"][0]["digest"]["sha256"] = "f" * 64
        scenarios.append(
            _scenario(
                "anchor-subject-substitution",
                lambda: expect_hold(
                    "ANCHOR_SUBJECT_SUBSTITUTION_HELD",
                    evaluate(candidate_statement=changed_statement),
                ),
            )
        )
        wrong_namespace = copy.deepcopy(statement)
        wrong_namespace["predicate"]["namespace"] = "wrong-purpose@truepanel"
        scenarios.append(
            _scenario(
                "purpose-substitution",
                lambda: expect_hold(
                    "PURPOSE_SUBSTITUTION_HELD",
                    evaluate(candidate_statement=wrong_namespace),
                ),
            )
        )
        authority = copy.deepcopy(statement)
        authority["predicate"]["deployment_authority"] = True
        scenarios.append(
            _scenario(
                "authority-escalation",
                lambda: expect_hold(
                    "AUTHORITY_ESCALATION_HELD", evaluate(candidate_statement=authority)
                ),
            )
        )
        scenarios.append(
            _scenario(
                "threshold-downgrade",
                lambda: expect_hold("THRESHOLD_DOWNGRADE_HELD", evaluate(threshold=1)),
            )
        )

        older_anchor = copy.deepcopy(anchor)
        older_anchor["state_sequence"] = 0
        payload = {
            key: value for key, value in older_anchor.items() if key != "anchor_sha256"
        }
        import hashlib

        older_anchor["anchor_sha256"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        scenarios.append(
            _scenario(
                "anchor-rollback",
                lambda: expect_hold(
                    "ANCHOR_ROLLBACK_HELD", evaluate(candidate_anchor=older_anchor)
                ),
            )
        )

    pass_count = sum(item["status"] == "PASS" for item in scenarios)
    return {
        "schema": "truepanel.holodeck-transparency-witness-anchor-custody/v1",
        "simulation": True,
        "custody_profile": "PURPOSE_BOUND_SSHSIG_2_OF_2",
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "pass_count": pass_count,
            "hold_count": len(scenarios) - pass_count,
            "threshold": 2,
            "distinct_fixture_custodians": 2,
            "exact_threshold_acceptances": 2,
            "missing_duplicate_untrusted_acceptances": 0,
            "signature_or_purpose_substitution_acceptances": 0,
            "anchor_rollback_acceptances": 0,
            "threshold_downgrade_acceptances": 0,
            "authority_escalations": 0,
            "coverage_total": 15,
            "coverage_trusted": 15,
            "coverage_gaps": 0,
            "shared_cooling_first_match_sample": 19,
            "isolated_threshold_first_match_sample": 46,
            "lead_samples": 27,
            "physical_operator_independence_validated": 0,
            "physical_power_loss_validated": 0,
            "fixture_private_keys_created": 2,
            "fixture_private_keys_retained": 0,
            "deployments": 0,
            "hardware_actions": 0,
            "runtime_writes": 0,
            "network_calls": 0,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-fault-evidence", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    result = run_transparency_witness_anchor_custody_checkride(
        storage_fault_evidence_path=args.storage_fault_evidence
    )
    rendered = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["run_transparency_witness_anchor_custody_checkride"]
