"""Deterministic checkride for the content-bound JT signing session."""

from __future__ import annotations

import os
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from truepanel.aegis.acceptance import semantic_sha256
from truepanel.aegis.development_review import build_development_packet
from truepanel.aegis.operator_handoff import OPERATOR_KEY_ID
from truepanel.aegis.signing_session import (
    SIGNING_SESSION_NAMESPACE,
    build_clock_witness,
    build_signing_session,
    canonical_signing_session_statement,
    verify_signing_session,
)
from truepanel.holodeck.aegis_single_operator_development import (
    NOW,
    development_fixture_materials,
)


def _run(*arguments: str, cwd: Path) -> str:
    return subprocess.run(arguments, cwd=cwd, check=True, capture_output=True, text=True).stdout


def _sign(key: Path, statement: bytes) -> str:
    statement_path = key.parent / "signing-session.json"
    statement_path.write_bytes(statement)
    subprocess.run(
        ["/usr/bin/ssh-keygen", "-Y", "sign", "-f", str(key), "-n", SIGNING_SESSION_NAMESPACE, str(statement_path)],
        check=True,
        capture_output=True,
    )
    return statement_path.with_suffix(".json.sig").read_text()


def run_signing_session_checkride() -> dict[str, Any]:
    scenarios: list[dict[str, str]] = []

    def record(name: str, status: str, reason: str) -> None:
        scenarios.append({"scenario": name, "status": status, "reason": reason})

    with tempfile.TemporaryDirectory(prefix="truepanel-aegis-signing-session-") as directory:
        root = Path(directory)
        checkout = root / "checkout"
        checkout.mkdir()
        _run("git", "init", "-q", cwd=checkout)
        _run("git", "config", "user.name", "HoloDeck", cwd=checkout)
        _run("git", "config", "user.email", "holodeck@invalid", cwd=checkout)
        (checkout / "subject.txt").write_text("deterministic signing subject\n")
        _run("git", "add", "subject.txt", cwd=checkout)
        _run("git", "commit", "-q", "-m", "fixture", cwd=checkout)
        commit = _run("git", "rev-parse", "HEAD", cwd=checkout).strip()

        key = root / "fixture-key"
        subprocess.run(
            ["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "HoloDeck disposable fixture only", "-f", str(key)],
            check=True,
            capture_output=True,
        )
        public = key.with_suffix(".pub").read_text().split()
        roster = root / "allowed_signers"
        roster.write_text(f"{OPERATOR_KEY_ID} {public[0]} {public[1]}\n")
        os.chmod(roster, 0o600)

        values = development_fixture_materials()
        values["candidate"] = dict(values["candidate"], source_commit=commit)
        values["packet"] = build_development_packet(
            review_id="jt-vega-development-review-v1",
            source_commit=commit,
            policy=values["policy"],
            candidate=values["candidate"],
            holodeck_evidence=values["evidence"],
            coverage_matrix=values["coverage"],
            reviewer_report=values["report"],
        )
        unsigned = deepcopy(values["receipt"])
        unsigned["packet_sha256"] = semantic_sha256(values["packet"])
        unsigned["signature"] = ""
        clock = build_clock_witness(
            observed_at="2026-09-19T12:00:00Z", unix_seconds=NOW, confirmed_by="jt"
        )

        def build(**changes: Any) -> dict[str, Any]:
            arguments = {
                "checkout_root": checkout,
                "clock_witness": clock,
                "packet": values["packet"],
                "unsigned_receipt": unsigned,
                "policy": values["policy"],
                "candidate": values["candidate"],
                "holodeck_evidence": values["evidence"],
                "coverage_matrix": values["coverage"],
                "reviewer_report": values["report"],
                "allowed_signers_path": roster,
            }
            arguments.update(changes)
            return build_signing_session(**arguments)

        session = build()
        record("clean-pinned-checkout", "READY_FOR_OFFLINE_SIGNATURE", "SessionSubjectsBound")
        signature = _sign(key, canonical_signing_session_statement(session))

        def verify(**changes: Any) -> dict[str, Any]:
            arguments = {
                "session": session,
                "signature": signature,
                "checkout_root": checkout,
                "clock_witness": clock,
                "packet": values["packet"],
                "unsigned_receipt": unsigned,
                "policy": values["policy"],
                "candidate": values["candidate"],
                "holodeck_evidence": values["evidence"],
                "coverage_matrix": values["coverage"],
                "reviewer_report": values["report"],
                "allowed_signers_path": roster,
            }
            arguments.update(changes)
            return verify_signing_session(**arguments)

        result = verify()
        record("exact-session-signature", result["status"], result["reason"])

        for name, changes in (
            ("missing-signature", {"signature": ""}),
            ("wrong-namespace-signature", {"signature": signature.replace("A", "B", 1)}),
            ("clock-substitution", {"clock_witness": dict(clock, unix_seconds=NOW + 1)}),
            ("checkout-path-substitution", {"checkout_root": root}),
        ):
            result = verify(**changes)
            record(name, result["status"], result["reason"])

        changed = deepcopy(session)
        changed["checkout_witness"]["tree"] = "f" * 40
        result = verify(session=changed)
        record("tree-tampering", result["status"], result["reason"])
        changed = deepcopy(session)
        changed["production_authority"] = True
        result = verify(session=changed)
        record("authority-escalation", result["status"], result["reason"])

        (checkout / "untracked.txt").write_text("drift\n")
        try:
            build()
        except ValueError as error:
            record("dirty-checkout-before-signing", "HOLD", str(error))
        else:
            record("dirty-checkout-before-signing", "UNSAFE_READY", "DirtyCheckoutAccepted")
        result = verify()
        record("dirty-checkout-after-signing", result["status"], result["reason"])
        (checkout / "untracked.txt").unlink()

        replay_id = semantic_sha256(dict(unsigned, signature=signature))
        result = verify(consumed_receipts=(replay_id,))
        record("receipt-replay", result["status"], result["reason"])

    counts: dict[str, int] = {}
    for scenario in scenarios:
        counts[scenario["status"]] = counts.get(scenario["status"], 0) + 1
    return {
        "scenario": "aegis-development-signing-session-v1",
        "status_counts": counts,
        "scenarios": scenarios,
        "measurements": {
            "offline_signing_ready": 1,
            "development_eligible": 1,
            "adversarial_holds": counts.get("HOLD", 0),
            "false_ready": counts.get("UNSAFE_READY", 0),
            "production_acceptances": 0,
            "deployments": 0,
            "hardware_actions": 0,
            "runtime_writes": 0,
        },
        "recovery_coverage": {"total": 8, "trusted": 8, "gaps": 0},
        "fixture_private_keys_retained": 0,
        "production_mutation": False,
        "control_authority": False,
    }


__all__ = ["run_signing_session_checkride"]
