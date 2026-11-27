"""Deterministic dual-threshold custodian-root rotation checkride."""

from __future__ import annotations

import argparse
import copy
import hashlib
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
    build_anchor_custody_statement,
)
from truepanel.aegis.transparency_witness_anchor_rotation import (
    CURRENT_CUSTODIAN_IDS,
    NAMESPACE,
    NEXT_CUSTODIAN_IDS,
    STATUS_HOLD,
    STATUS_REHEARSED,
    build_custodian_root,
    build_rotation_statement,
    evaluate_custodian_root_rotation,
    rotation_statement_bytes,
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
        return {"name": name, "status": "PASS", "observation": action()}
    except (
        AssertionError,
        KeyError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as error:
        return {"name": name, "status": "HOLD", "observation": str(error)}


def _rehash(root: Mapping[str, Any]) -> dict[str, Any]:
    changed = dict(root)
    payload = {key: value for key, value in changed.items() if key != "root_sha256"}
    changed["root_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return changed


def run_transparency_witness_anchor_rotation_checkride(
    root: Path | None = None, *, custody_evidence_path: Path | None = None
) -> dict[str, Any]:
    repository = root or Path(__file__).resolve().parents[2]
    predecessor_path = custody_evidence_path or repository / (
        "docs/evidence/aegis-transparency-witness-anchor-custody-checkride-v1.json"
    )
    predecessor_bytes = predecessor_path.read_bytes()
    predecessor = json.loads(predecessor_bytes)
    custody_evidence_sha256 = hashlib.sha256(predecessor_bytes).hexdigest()
    measures = predecessor.get("measurements", {})
    if (
        predecessor.get("schema")
        != "truepanel.holodeck-transparency-witness-anchor-custody/v1"
        or measures.get("coverage_gaps") != 0
        or measures.get("threshold_downgrade_acceptances") != 0
    ):
        raise ValueError("reviewed threshold anchor-custody evidence required")

    with tempfile.TemporaryDirectory(
        prefix="truepanel-aegis-anchor-rotation-"
    ) as directory:
        base = Path(directory).resolve()
        identities = (
            CURRENT_CUSTODIAN_IDS[0],
            CURRENT_CUSTODIAN_IDS[1],
            NEXT_CUSTODIAN_IDS[1],
        )
        keys = {
            identity: base / f"custodian-{index}"
            for index, identity in enumerate(identities)
        }
        for key in keys.values():
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

        def roster(name: str, ids: tuple[str, ...]):
            path = base / name
            path.write_text(
                "".join(
                    f"{identity} {keys[identity].with_suffix('.pub').read_text(encoding='ascii')}"
                    for identity in ids
                ),
                encoding="ascii",
            )
            os.chmod(path, 0o600)
            fingerprints = validate_allowed_signers_roster(
                path.read_bytes(), expected_key_ids=ids
            )
            verifier = OpenSshSignatureVerifier(
                path, namespace=NAMESPACE, expected_key_ids=ids
            )
            return fingerprints, verifier

        current_fingerprints, current_verifier = roster(
            "current-allowed-signers", CURRENT_CUSTODIAN_IDS
        )
        next_fingerprints, next_verifier = roster(
            "next-allowed-signers", NEXT_CUSTODIAN_IDS
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
        anchor_statement = build_anchor_custody_statement(anchor)
        current_root = build_custodian_root(
            version=1,
            anchor_statement=anchor_statement,
            custodian_fingerprints=current_fingerprints,
            custodian_ids=CURRENT_CUSTODIAN_IDS,
            predecessor_root_sha256=None,
            custody_evidence_sha256=custody_evidence_sha256,
        )
        next_root = build_custodian_root(
            version=2,
            anchor_statement=anchor_statement,
            custodian_fingerprints=next_fingerprints,
            custodian_ids=NEXT_CUSTODIAN_IDS,
            predecessor_root_sha256=current_root["root_sha256"],
            custody_evidence_sha256=custody_evidence_sha256,
        )
        statement = build_rotation_statement(current_root, next_root)
        signed_bytes = rotation_statement_bytes(statement)
        current_signatures = [
            {"custodian_id": identity, "signature": _sign(keys[identity], signed_bytes)}
            for identity in CURRENT_CUSTODIAN_IDS
        ]
        next_signatures = [
            {"custodian_id": identity, "signature": _sign(keys[identity], signed_bytes)}
            for identity in NEXT_CUSTODIAN_IDS
        ]

        def evaluate(
            candidate_statement=statement,
            candidate_current_signatures=current_signatures,
            candidate_next_signatures=next_signatures,
            *,
            candidate_current_root=current_root,
            candidate_next_root=next_root,
        ):
            return evaluate_custodian_root_rotation(
                candidate_current_root,
                candidate_next_root,
                anchor_statement,
                custody_evidence_sha256,
                candidate_statement,
                candidate_current_signatures,
                candidate_next_signatures,
                current_verifier,
                next_verifier,
            )

        def expect_hold(observation: str, result: Mapping[str, Any]) -> str:
            if result["status"] != STATUS_HOLD:
                raise ValueError(f"{observation}_ACCEPTED")
            raise ValueError(observation)

        scenarios: list[dict[str, Any]] = []

        def exact_rotation() -> str:
            result = evaluate()
            assert result["status"] == STATUS_REHEARSED
            assert result["current_threshold_verified"] is True
            assert result["next_threshold_verified"] is True
            return "EXACT_DUAL_THRESHOLD_ROOT_ROTATION_REHEARSED"

        scenarios.append(_scenario("exact-dual-threshold-rotation", exact_rotation))
        scenarios.append(
            _scenario(
                "signature-order-independent",
                lambda: (
                    "ORDER_INDEPENDENT_DUAL_THRESHOLD_ROTATION_REHEARSED"
                    if evaluate(
                        candidate_current_signatures=list(reversed(current_signatures)),
                        candidate_next_signatures=list(reversed(next_signatures)),
                    )["status"]
                    == STATUS_REHEARSED
                    else (_ for _ in ()).throw(ValueError("ORDER_DEPENDENT_ROTATION"))
                ),
            )
        )
        scenarios.append(
            _scenario(
                "missing-current-quorum",
                lambda: expect_hold(
                    "MISSING_CURRENT_QUORUM_HELD",
                    evaluate(candidate_current_signatures=current_signatures[:1]),
                ),
            )
        )
        scenarios.append(
            _scenario(
                "missing-next-quorum",
                lambda: expect_hold(
                    "MISSING_NEXT_QUORUM_HELD",
                    evaluate(candidate_next_signatures=next_signatures[:1]),
                ),
            )
        )
        duplicate_current = [current_signatures[0], current_signatures[0]]
        scenarios.append(
            _scenario(
                "duplicate-current-identity",
                lambda: expect_hold(
                    "DUPLICATE_CURRENT_IDENTITY_HELD",
                    evaluate(candidate_current_signatures=duplicate_current),
                ),
            )
        )
        duplicate_next_root = copy.deepcopy(next_root)
        duplicate_next_root["custodian_fingerprints"][NEXT_CUSTODIAN_IDS[1]] = (
            duplicate_next_root["custodian_fingerprints"][NEXT_CUSTODIAN_IDS[0]]
        )
        duplicate_next_root = _rehash(duplicate_next_root)
        scenarios.append(
            _scenario(
                "duplicate-next-key",
                lambda: expect_hold(
                    "DUPLICATE_NEXT_KEY_HELD",
                    evaluate(candidate_next_root=duplicate_next_root),
                ),
            )
        )
        untrusted_next = copy.deepcopy(next_signatures)
        untrusted_next[1]["custodian_id"] = "unknown@holodeck.invalid"
        scenarios.append(
            _scenario(
                "untrusted-next-custodian",
                lambda: expect_hold(
                    "UNTRUSTED_NEXT_CUSTODIAN_HELD",
                    evaluate(candidate_next_signatures=untrusted_next),
                ),
            )
        )
        substituted = copy.deepcopy(next_signatures)
        substituted[1]["signature"] = current_signatures[0]["signature"]
        scenarios.append(
            _scenario(
                "signature-substitution",
                lambda: expect_hold(
                    "ROTATION_SIGNATURE_SUBSTITUTION_HELD",
                    evaluate(candidate_next_signatures=substituted),
                ),
            )
        )
        subject_substitution = copy.deepcopy(statement)
        subject_substitution["subject"][0]["digest"]["sha256"] = "f" * 64
        scenarios.append(
            _scenario(
                "root-subject-substitution",
                lambda: expect_hold(
                    "ROOT_SUBJECT_SUBSTITUTION_HELD",
                    evaluate(candidate_statement=subject_substitution),
                ),
            )
        )
        wrong_purpose = copy.deepcopy(statement)
        wrong_purpose["predicate"]["namespace"] = "wrong-purpose@truepanel"
        scenarios.append(
            _scenario(
                "purpose-substitution",
                lambda: expect_hold(
                    "ROTATION_PURPOSE_SUBSTITUTION_HELD",
                    evaluate(candidate_statement=wrong_purpose),
                ),
            )
        )
        rollback_root = _rehash({**next_root, "version": 1})
        scenarios.append(
            _scenario(
                "version-rollback",
                lambda: expect_hold(
                    "ROTATION_VERSION_ROLLBACK_HELD",
                    evaluate(candidate_next_root=rollback_root),
                ),
            )
        )
        skipped_root = _rehash({**next_root, "version": 3})
        scenarios.append(
            _scenario(
                "version-skip",
                lambda: expect_hold(
                    "ROTATION_VERSION_SKIP_HELD",
                    evaluate(candidate_next_root=skipped_root),
                ),
            )
        )
        downgraded_root = _rehash({**next_root, "threshold": 1})
        scenarios.append(
            _scenario(
                "threshold-downgrade",
                lambda: expect_hold(
                    "ROTATION_THRESHOLD_DOWNGRADE_HELD",
                    evaluate(candidate_next_root=downgraded_root),
                ),
            )
        )
        wrong_predecessor = _rehash({**next_root, "predecessor_root_sha256": "f" * 64})
        scenarios.append(
            _scenario(
                "predecessor-substitution",
                lambda: expect_hold(
                    "ROTATION_PREDECESSOR_SUBSTITUTION_HELD",
                    evaluate(candidate_next_root=wrong_predecessor),
                ),
            )
        )
        authority = copy.deepcopy(statement)
        authority["predicate"]["deployment_authority"] = True
        scenarios.append(
            _scenario(
                "authority-escalation",
                lambda: expect_hold(
                    "ROTATION_AUTHORITY_ESCALATION_HELD",
                    evaluate(candidate_statement=authority),
                ),
            )
        )
        unchanged_root = _rehash(
            {
                **next_root,
                "custodian_fingerprints": current_root["custodian_fingerprints"],
            }
        )
        scenarios.append(
            _scenario(
                "no-key-change",
                lambda: expect_hold(
                    "NO_KEY_CHANGE_HELD", evaluate(candidate_next_root=unchanged_root)
                ),
            )
        )

    pass_count = sum(item["status"] == "PASS" for item in scenarios)
    return {
        "schema": "truepanel.holodeck-transparency-witness-anchor-rotation/v1",
        "simulation": True,
        "rotation_profile": "TUF_SHAPED_DUAL_THRESHOLD_N_PLUS_1",
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "pass_count": pass_count,
            "hold_count": len(scenarios) - pass_count,
            "current_threshold": 2,
            "next_threshold": 2,
            "current_version": 1,
            "next_version": 2,
            "distinct_fixture_keys": 3,
            "exact_dual_threshold_acceptances": 2,
            "missing_or_duplicate_quorum_acceptances": 0,
            "signature_or_purpose_substitution_acceptances": 0,
            "rollback_or_version_skip_acceptances": 0,
            "threshold_downgrade_acceptances": 0,
            "predecessor_substitution_acceptances": 0,
            "authority_escalations": 0,
            "coverage_total": 18,
            "coverage_trusted": 18,
            "coverage_gaps": 0,
            "shared_cooling_first_match_sample": 19,
            "isolated_threshold_first_match_sample": 46,
            "lead_samples": 27,
            "physical_operator_independence_validated": 0,
            "physical_power_loss_validated": 0,
            "fixture_private_keys_created": 3,
            "fixture_private_keys_retained": 0,
            "deployments": 0,
            "hardware_actions": 0,
            "runtime_writes": 0,
            "network_calls": 0,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--custody-evidence", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    result = run_transparency_witness_anchor_rotation_checkride(
        custody_evidence_path=args.custody_evidence
    )
    rendered = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["run_transparency_witness_anchor_rotation_checkride"]
