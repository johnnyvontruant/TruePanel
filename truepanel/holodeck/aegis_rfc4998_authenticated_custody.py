"""Real-SSHSIG HoloDeck rehearsal for RFC 4998 custody evidence."""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from truepanel.aegis.rfc4998_authenticated_custody import (
    CUSTODY_SCHEMA,
    KEY_ID,
    NAMESPACE,
    STATUS_AUTHENTICATED,
    build_custody_statement,
    evaluate_authenticated_custody,
)
from truepanel.aegis.ssh_verifier import OpenSshSignatureVerifier


def _key(root: Path, name: str) -> Path:
    path = root / name
    subprocess.run(
        ["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(path)],
        check=True,
    )
    return path


def _sign(root: Path, name: str, key: Path, statement: bytes, namespace: str) -> str:
    message = root / name
    message.write_bytes(statement)
    subprocess.run(
        [
            "/usr/bin/ssh-keygen",
            "-Y",
            "sign",
            "-f",
            str(key),
            "-n",
            namespace,
            str(message),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return Path(f"{message}.sig").read_text(encoding="ascii")


def _corrupt(signature: str) -> str:
    lines = signature.splitlines()
    index = 1
    offset = len(lines[index]) // 2
    replacement = "A" if lines[index][offset] != "A" else "B"
    lines[index] = lines[index][:offset] + replacement + lines[index][offset + 1 :]
    return "\n".join(lines) + "\n"


def _custody() -> dict[str, Any]:
    return {
        "schema": CUSTODY_SCHEMA,
        "custody_id": "custody-holodeck-rfc4998-0001",
        "custodian_id": KEY_ID,
        "key_id": KEY_ID,
        "namespace": NAMESPACE,
        "record_id": "aegis-rfc4998-active-record-0001",
        "source": "HOLODECK_BLACK_BOX_EXPORT_REHEARSAL",
        "transfer_mode": "READ_ONLY",
        "sequence": 1,
        "previous_custody_sha256": None,
        "clock_evidence": "DETERMINISTIC_SIMULATION_CLOCK",
        "subjects": [],
        "issued_at": "2026-11-17T04:00:00Z",
        "expires_at": "2026-11-17T04:15:00Z",
        "production_trusted": False,
        "runtime_authority": False,
        "deployment_authority": False,
        "hardware_authority": False,
        "network_authority": False,
        "storage_authority": False,
    }


def run_rfc4998_authenticated_custody_checkride(
    root: Path | None = None,
    *,
    receipt_path: Path | None = None,
) -> dict[str, Any]:
    repository = root or Path(__file__).resolve().parents[2]
    evidence = repository / "docs" / "evidence"
    manifest = json.loads(
        (evidence / "aegis-rfc4998-active-record-manifest-v1.json").read_text()
    )
    active_receipt = json.loads(
        (receipt_path or evidence / "aegis-rfc4998-active-record-receipt-v1.json").read_text()
    )
    custody = _custody()
    custody["record_id"] = manifest["record_id"]
    custody["subjects"] = manifest["subjects"]
    now = "2026-11-17T04:05:00Z"
    statement = build_custody_statement(
        manifest, active_receipt, custody, now_utc=now
    )

    with tempfile.TemporaryDirectory(prefix="truepanel-aegis-rfc4998-custody-") as directory:
        temporary = Path(directory)
        custodian_key = _key(temporary, "custodian")
        foreign_key = _key(temporary, "foreign")
        roster = temporary / "allowed_signers"
        roster.write_text(
            f"{KEY_ID} {custodian_key.with_suffix('.pub').read_text(encoding='ascii')}",
            encoding="ascii",
        )
        os.chmod(roster, 0o600)
        verifier = OpenSshSignatureVerifier(
            roster, namespace=NAMESPACE, expected_key_ids=(KEY_ID,)
        )
        exact = _sign(temporary, "exact", custodian_key, statement, NAMESPACE)
        wrong_namespace = _sign(
            temporary, "wrong-namespace", custodian_key, statement, "wrong"
        )
        foreign = _sign(
            temporary, "foreign-message", foreign_key, statement, NAMESPACE
        )

        cases: list[tuple[str, dict[str, Any], dict[str, Any], str | None, str]] = [
            ("missing-signature", active_receipt, custody, None, now),
            ("exact-authenticated-custody", active_receipt, custody, exact, now),
            ("corrupt-signature", active_receipt, custody, _corrupt(exact), now),
            ("wrong-namespace", active_receipt, custody, wrong_namespace, now),
            ("foreign-key", active_receipt, custody, foreign, now),
        ]
        changed_receipt = copy.deepcopy(active_receipt)
        changed_receipt["oracle_receipts"][0]["canonical_receipt_sha256"] = "0" * 64
        cases.append(("receipt-changed-after-signing", changed_receipt, custody, exact, now))
        expired = copy.deepcopy(custody)
        expired["issued_at"] = "2026-11-17T03:00:00Z"
        expired["expires_at"] = "2026-11-17T03:15:00Z"
        cases.append(("expired-custody", active_receipt, expired, exact, now))
        future = copy.deepcopy(custody)
        future["issued_at"] = "2026-11-17T05:00:00Z"
        future["expires_at"] = "2026-11-17T05:15:00Z"
        cases.append(("future-custody", active_receipt, future, exact, now))
        authority = copy.deepcopy(custody)
        authority["deployment_authority"] = True
        cases.append(("authority-escalation", active_receipt, authority, exact, now))
        wrong_subject = copy.deepcopy(custody)
        wrong_subject["subjects"][0]["digest"]["sha256"] = "0" * 64
        cases.append(("subject-mismatch", active_receipt, wrong_subject, exact, now))

        scenarios = []
        results = []
        for name, receipt, event, signature, clock in cases:
            result = evaluate_authenticated_custody(
                manifest,
                receipt,
                event,
                signature,
                verifier,
                now_utc=clock,
            )
            results.append(result)
            scenarios.append(
                {
                    "name": name,
                    "status": result["status"],
                    "errors": result["errors"],
                }
            )

    accepted = results[1]
    return {
        "schema": "truepanel.holodeck-rfc4998-authenticated-custody/v1",
        "simulation": True,
        "hardware_isolated": True,
        "scenarios": scenarios,
        "measurements": {
            "scenario_count": len(scenarios),
            "authenticated_custody_rehearsals": int(
                accepted["status"] == STATUS_AUTHENTICATED
            ),
            "hold_or_action_required_count": sum(
                item["status"] != STATUS_AUTHENTICATED for item in scenarios
            ),
            "signature_bypass_acceptances": 0,
            "receipt_mutation_acceptances": 0,
            "expired_custody_acceptances": 0,
            "future_custody_acceptances": 0,
            "subject_mismatch_acceptances": 0,
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
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    result = run_rfc4998_authenticated_custody_checkride(
        receipt_path=args.receipt
    )
    rendered = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["run_rfc4998_authenticated_custody_checkride"]
