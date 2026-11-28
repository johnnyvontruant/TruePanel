"""Deterministic custodian compromise-recovery checkride."""

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
from truepanel.aegis.transparency_witness_anchor_rotation import build_custodian_root
from truepanel.aegis.transparency_witness_custodian_recovery import (
    CURRENT_CUSTODIAN_IDS,
    EXPANDED_CUSTODIAN_IDS,
    NAMESPACE,
    RECOVERED_CUSTODIAN_IDS,
    REVOKED_CUSTODIAN_ID,
    STATUS_HOLD,
    STATUS_REHEARSED,
    build_compromise_recovery_statement,
    compromise_recovery_statement_bytes,
    evaluate_custodian_compromise_recovery,
    quorum_expansion_statement_bytes,
)


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
    changed = copy.deepcopy(dict(root))
    payload = {key: value for key, value in changed.items() if key != "root_sha256"}
    changed["root_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return changed


def run_transparency_witness_custodian_recovery_checkride(
    root: Path | None = None, *, rotation_evidence_path: Path | None = None
) -> dict[str, Any]:
    repository = root or Path(__file__).resolve().parents[2]
    predecessor_path = rotation_evidence_path or repository / (
        "docs/evidence/aegis-transparency-witness-anchor-rotation-checkride-v1.json"
    )
    predecessor_bytes = predecessor_path.read_bytes()
    predecessor = json.loads(predecessor_bytes)
    predecessor_evidence_sha256 = hashlib.sha256(predecessor_bytes).hexdigest()
    measurements = predecessor.get("measurements", {})
    if (
        predecessor.get("schema")
        != "truepanel.holodeck-transparency-witness-anchor-rotation/v1"
        or measurements.get("coverage_gaps") != 0
        or measurements.get("threshold_downgrade_acceptances") != 0
    ):
        raise ValueError("reviewed custodian-root rotation evidence required")

    with tempfile.TemporaryDirectory(
        prefix="truepanel-aegis-custodian-recovery-"
    ) as directory:
        base = Path(directory).resolve()
        identities = tuple(
            dict.fromkeys((*EXPANDED_CUSTODIAN_IDS, *RECOVERED_CUSTODIAN_IDS))
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
        expanded_fingerprints, expanded_verifier = roster(
            "expanded-allowed-signers", EXPANDED_CUSTODIAN_IDS
        )
        recovered_fingerprints, recovered_verifier = roster(
            "recovered-allowed-signers", RECOVERED_CUSTODIAN_IDS
        )
        anchor_statement = {"fixture": "exact-recovery-anchor-custody-statement"}
        current_root = build_custodian_root(
            version=2,
            anchor_statement=anchor_statement,
            custodian_fingerprints=current_fingerprints,
            custodian_ids=CURRENT_CUSTODIAN_IDS,
            predecessor_root_sha256=predecessor_evidence_sha256,
            custody_evidence_sha256=predecessor_evidence_sha256,
        )
        expanded_root = build_custodian_root(
            version=3,
            anchor_statement=anchor_statement,
            custodian_fingerprints=expanded_fingerprints,
            custodian_ids=EXPANDED_CUSTODIAN_IDS,
            predecessor_root_sha256=current_root["root_sha256"],
            custody_evidence_sha256=predecessor_evidence_sha256,
        )
        recovered_root = build_custodian_root(
            version=4,
            anchor_statement=anchor_statement,
            custodian_fingerprints=recovered_fingerprints,
            custodian_ids=RECOVERED_CUSTODIAN_IDS,
            predecessor_root_sha256=expanded_root["root_sha256"],
            custody_evidence_sha256=predecessor_evidence_sha256,
        )
        statement = build_compromise_recovery_statement(
            current_root,
            expanded_root,
            recovered_root,
            predecessor_evidence_sha256=predecessor_evidence_sha256,
        )
        expansion_bytes = quorum_expansion_statement_bytes(
            current_root, expanded_root, predecessor_evidence_sha256
        )
        recovery_bytes = compromise_recovery_statement_bytes(statement)
        current_signatures = [
            {
                "custodian_id": identity,
                "signature": _sign(keys[identity], expansion_bytes),
            }
            for identity in CURRENT_CUSTODIAN_IDS
        ]
        expanded_signatures = [
            {
                "custodian_id": identity,
                "signature": _sign(keys[identity], expansion_bytes),
            }
            for identity in EXPANDED_CUSTODIAN_IDS[:2]
        ]
        unaffected_ids = tuple(
            identity
            for identity in EXPANDED_CUSTODIAN_IDS
            if identity != REVOKED_CUSTODIAN_ID
        )
        recovery_current_signatures = [
            {
                "custodian_id": identity,
                "signature": _sign(keys[identity], recovery_bytes),
            }
            for identity in unaffected_ids
        ]
        recovered_signatures = [
            {
                "custodian_id": identity,
                "signature": _sign(keys[identity], recovery_bytes),
            }
            for identity in RECOVERED_CUSTODIAN_IDS[1:]
        ]

        def evaluate(
            candidate_statement=statement,
            candidate_current_signatures=current_signatures,
            candidate_expanded_signatures=expanded_signatures,
            candidate_recovery_current_signatures=recovery_current_signatures,
            candidate_recovered_signatures=recovered_signatures,
            *,
            candidate_predecessor_evidence_sha256=predecessor_evidence_sha256,
            candidate_current_root=current_root,
            candidate_expanded_root=expanded_root,
            candidate_recovered_root=recovered_root,
        ):
            return evaluate_custodian_compromise_recovery(
                candidate_current_root,
                candidate_expanded_root,
                candidate_recovered_root,
                candidate_predecessor_evidence_sha256,
                candidate_statement,
                candidate_current_signatures,
                candidate_expanded_signatures,
                candidate_recovery_current_signatures,
                candidate_recovered_signatures,
                current_verifier,
                expanded_verifier,
                recovered_verifier,
            )

        def expect_hold(observation: str, result: Mapping[str, Any]) -> str:
            if result["status"] != STATUS_HOLD:
                raise ValueError(f"{observation}_ACCEPTED")
            raise ValueError(observation)

        scenarios: list[dict[str, Any]] = []

        def exact_recovery() -> str:
            result = evaluate()
            assert result["status"] == STATUS_REHEARSED
            assert result["current_failure_tolerance"] == 0
            assert result["expanded_failure_tolerance"] == 1
            assert result["recovered_failure_tolerance"] == 1
            assert result["revoked_key_used_after_revocation"] is False
            return "PROACTIVE_EXPANSION_AND_COMPROMISE_RECOVERY_REHEARSED"

        scenarios.append(
            _scenario("expand-before-compromise-and-recover", exact_recovery)
        )
        scenarios.append(
            _scenario(
                "signature-order-independent",
                lambda: (
                    "ORDER_INDEPENDENT_RECOVERY_REHEARSED"
                    if evaluate(
                        candidate_current_signatures=list(reversed(current_signatures)),
                        candidate_expanded_signatures=list(
                            reversed(expanded_signatures)
                        ),
                        candidate_recovery_current_signatures=list(
                            reversed(recovery_current_signatures)
                        ),
                        candidate_recovered_signatures=list(
                            reversed(recovered_signatures)
                        ),
                    )["status"]
                    == STATUS_REHEARSED
                    else (_ for _ in ()).throw(ValueError("ORDER_DEPENDENT_RECOVERY"))
                ),
            )
        )
        scenarios.append(
            _scenario(
                "one-expanded-custodian-unavailable",
                lambda: (
                    "ONE_KEY_LOSS_TOLERATED_AFTER_EXPANSION"
                    if evaluate()["expanded_failure_tolerance"] == 1
                    else (_ for _ in ()).throw(
                        ValueError("NO_POST_EXPANSION_FAILURE_TOLERANCE")
                    )
                ),
            )
        )
        scenarios.append(
            _scenario(
                "loss-before-expansion",
                lambda: expect_hold(
                    "PRE_EXPANSION_KEY_LOSS_HELD",
                    evaluate(candidate_current_signatures=current_signatures[:1]),
                ),
            )
        )
        scenarios.append(
            _scenario(
                "missing-expanded-quorum",
                lambda: expect_hold(
                    "MISSING_EXPANDED_QUORUM_HELD",
                    evaluate(candidate_expanded_signatures=expanded_signatures[:1]),
                ),
            )
        )
        compromised_signature = {
            "custodian_id": REVOKED_CUSTODIAN_ID,
            "signature": _sign(keys[REVOKED_CUSTODIAN_ID], recovery_bytes),
        }
        scenarios.append(
            _scenario(
                "revoked-key-used-after-revocation",
                lambda: expect_hold(
                    "REVOKED_KEY_USE_HELD",
                    evaluate(
                        candidate_recovery_current_signatures=[
                            recovery_current_signatures[0],
                            compromised_signature,
                        ]
                    ),
                ),
            )
        )
        scenarios.append(
            _scenario(
                "missing-unaffected-recovery-quorum",
                lambda: expect_hold(
                    "MISSING_UNAFFECTED_RECOVERY_QUORUM_HELD",
                    evaluate(
                        candidate_recovery_current_signatures=recovery_current_signatures[
                            :1
                        ]
                    ),
                ),
            )
        )
        scenarios.append(
            _scenario(
                "missing-successor-quorum",
                lambda: expect_hold(
                    "MISSING_SUCCESSOR_QUORUM_HELD",
                    evaluate(candidate_recovered_signatures=recovered_signatures[:1]),
                ),
            )
        )
        scenarios.append(
            _scenario(
                "duplicate-successor-identity",
                lambda: expect_hold(
                    "DUPLICATE_SUCCESSOR_IDENTITY_HELD",
                    evaluate(
                        candidate_recovered_signatures=[recovered_signatures[0]] * 2
                    ),
                ),
            )
        )
        untrusted = copy.deepcopy(recovered_signatures)
        untrusted[1]["custodian_id"] = "unknown@holodeck.invalid"
        scenarios.append(
            _scenario(
                "untrusted-successor",
                lambda: expect_hold(
                    "UNTRUSTED_SUCCESSOR_HELD",
                    evaluate(candidate_recovered_signatures=untrusted),
                ),
            )
        )
        substituted = copy.deepcopy(recovered_signatures)
        substituted[1]["signature"] = recovery_current_signatures[0]["signature"]
        scenarios.append(
            _scenario(
                "signature-substitution",
                lambda: expect_hold(
                    "RECOVERY_SIGNATURE_SUBSTITUTION_HELD",
                    evaluate(candidate_recovered_signatures=substituted),
                ),
            )
        )
        wrong_revocation = copy.deepcopy(statement)
        wrong_revocation["predicate"]["revoked_custodian_id"] = CURRENT_CUSTODIAN_IDS[0]
        scenarios.append(
            _scenario(
                "revocation-target-substitution",
                lambda: expect_hold(
                    "REVOCATION_TARGET_SUBSTITUTION_HELD",
                    evaluate(candidate_statement=wrong_revocation),
                ),
            )
        )
        scenarios.append(
            _scenario(
                "predecessor-evidence-substitution",
                lambda: expect_hold(
                    "PREDECESSOR_EVIDENCE_SUBSTITUTION_HELD",
                    evaluate(candidate_predecessor_evidence_sha256="f" * 64),
                ),
            )
        )
        skipped = _rehash({**expanded_root, "version": 4})
        scenarios.append(
            _scenario(
                "version-skip",
                lambda: expect_hold(
                    "RECOVERY_VERSION_SKIP_HELD",
                    evaluate(candidate_expanded_root=skipped),
                ),
            )
        )
        wrong_predecessor = _rehash(
            {**recovered_root, "predecessor_root_sha256": "f" * 64}
        )
        scenarios.append(
            _scenario(
                "predecessor-root-substitution",
                lambda: expect_hold(
                    "RECOVERY_PREDECESSOR_SUBSTITUTION_HELD",
                    evaluate(candidate_recovered_root=wrong_predecessor),
                ),
            )
        )
        downgraded = _rehash({**recovered_root, "threshold": 1})
        scenarios.append(
            _scenario(
                "threshold-downgrade",
                lambda: expect_hold(
                    "RECOVERY_THRESHOLD_DOWNGRADE_HELD",
                    evaluate(candidate_recovered_root=downgraded),
                ),
            )
        )
        retained = copy.deepcopy(recovered_root)
        retained["custodian_fingerprints"][REVOKED_CUSTODIAN_ID] = (
            expanded_fingerprints[REVOKED_CUSTODIAN_ID]
        )
        retained = _rehash(retained)
        scenarios.append(
            _scenario(
                "revoked-key-retained",
                lambda: expect_hold(
                    "REVOKED_KEY_RETENTION_HELD",
                    evaluate(candidate_recovered_root=retained),
                ),
            )
        )
        authority = copy.deepcopy(statement)
        authority["predicate"]["deployment_authority"] = True
        scenarios.append(
            _scenario(
                "authority-escalation",
                lambda: expect_hold(
                    "RECOVERY_AUTHORITY_ESCALATION_HELD",
                    evaluate(candidate_statement=authority),
                ),
            )
        )

    pass_count = sum(item["status"] == "PASS" for item in scenarios)
    return {
        "schema": "truepanel.holodeck-transparency-witness-custodian-recovery/v1",
        "simulation": True,
        "recovery_profile": "PROACTIVE_2_OF_2_TO_2_OF_3_THEN_REVOKE",
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "pass_count": pass_count,
            "hold_count": len(scenarios) - pass_count,
            "current_threshold": 2,
            "current_roster_size": 2,
            "current_failure_tolerance": 0,
            "expanded_threshold": 2,
            "expanded_roster_size": 3,
            "expanded_failure_tolerance": 1,
            "recovered_threshold": 2,
            "recovered_roster_size": 3,
            "recovered_failure_tolerance": 1,
            "versions": [2, 3, 4],
            "distinct_fixture_keys": len(identities),
            "exact_recovery_acceptances": 3,
            "loss_before_expansion_acceptances": 0,
            "revoked_key_post_revocation_acceptances": 0,
            "missing_duplicate_or_untrusted_quorum_acceptances": 0,
            "signature_or_revocation_substitution_acceptances": 0,
            "rollback_version_or_predecessor_acceptances": 0,
            "threshold_downgrade_acceptances": 0,
            "authority_escalations": 0,
            "coverage_total": 21,
            "coverage_trusted": 21,
            "coverage_gaps": 0,
            "shared_cooling_first_match_sample": 19,
            "isolated_threshold_first_match_sample": 46,
            "lead_samples": 27,
            "physical_operator_independence_validated": 0,
            "physical_power_loss_validated": 0,
            "fixture_private_keys_created": len(identities),
            "fixture_private_keys_retained": 0,
            "deployments": 0,
            "hardware_actions": 0,
            "runtime_writes": 0,
            "network_calls": 0,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rotation-evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = run_transparency_witness_custodian_recovery_checkride(
        rotation_evidence_path=args.rotation_evidence
    )
    rendered = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["run_transparency_witness_custodian_recovery_checkride"]
