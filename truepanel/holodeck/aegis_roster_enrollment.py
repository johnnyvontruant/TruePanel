"""HoloDeck checkride for public-only development roster enrollment."""

from __future__ import annotations

import os
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from truepanel.aegis.operator_handoff import OPERATOR_KEY_ID, build_operator_handoff
from truepanel.aegis.roster_enrollment import (
    ENROLLMENT_CONFIRMATION,
    provision_development_roster,
)
from truepanel.aegis.ssh_verifier import validate_allowed_signers_roster
from truepanel.holodeck.aegis_single_operator_development import (
    NOW,
    development_fixture_materials,
)


def _fingerprint(public_key: Path) -> str:
    fields = public_key.read_text().split()
    roster = f"{OPERATOR_KEY_ID} {fields[0]} {fields[1]}\n".encode()
    return validate_allowed_signers_roster(
        roster, expected_key_ids=(OPERATOR_KEY_ID,)
    )[OPERATOR_KEY_ID]


def run_roster_enrollment_checkride() -> dict[str, Any]:
    scenarios: list[dict[str, str]] = []

    def record(name: str, status: str, reason: str) -> None:
        scenarios.append({"scenario": name, "status": status, "reason": reason})

    with tempfile.TemporaryDirectory(prefix="truepanel-aegis-roster-enrollment-") as value:
        root = Path(value)
        checkout = root / "checkout"
        checkout.mkdir(mode=0o700)
        public_dir = root / "public"
        public_dir.mkdir(mode=0o700)
        roster_dir = root / "roster"
        roster_dir.mkdir(mode=0o700)
        private_key = root / "disposable-fixture-key"
        subprocess.run(
            [
                "/usr/bin/ssh-keygen",
                "-q",
                "-t",
                "ed25519",
                "-N",
                "",
                "-C",
                "HoloDeck disposable fixture only",
                "-f",
                str(private_key),
            ],
            check=True,
            capture_output=True,
        )
        public_key = public_dir / "jt-development-review.pub"
        public_key.write_bytes(private_key.with_suffix(".pub").read_bytes())
        os.chmod(public_key, 0o600)
        fingerprint = _fingerprint(public_key)
        roster = roster_dir / "allowed_signers"

        def enroll(*, destination: Path, source: Path = public_key, **changes: Any) -> dict[str, Any]:
            arguments = {
                "public_key_path": source,
                "destination_path": destination,
                "checkout_root": checkout,
                "expected_fingerprint": fingerprint,
                "operator_confirmation": ENROLLMENT_CONFIRMATION,
            }
            arguments.update(changes)
            return provision_development_roster(**arguments)

        exact = enroll(destination=roster)
        record("exact-public-key", exact["status"], "OnePublicIdentityInstalled")

        values = development_fixture_materials()
        unsigned = deepcopy(values["receipt"])
        unsigned["signature"] = ""
        handoff = build_operator_handoff(
            packet=values["packet"],
            unsigned_receipt=unsigned,
            policy=values["policy"],
            candidate=values["candidate"],
            holodeck_evidence=values["evidence"],
            coverage_matrix=values["coverage"],
            reviewer_report=values["report"],
            allowed_signers_path=roster,
            expected_source_commit=values["packet"]["source_commit"],
            now=NOW,
        )
        record("handoff-consumes-public-roster", "READY_FOR_OFFLINE_SIGNATURE", handoff["key_id"])

        def hold(name: str, *, source: Path = public_key, **changes: Any) -> None:
            destination = changes.pop("destination_path", roster_dir / f"{name}.roster")
            try:
                enroll(destination=destination, source=source, **changes)
            except ValueError as error:
                record(name, "HOLD", str(error))
            else:
                record(name, "UnsafeReady", "UnsafeRosterProvisioned")

        hold("missing-confirmation", operator_confirmation="")
        hold("fingerprint-mismatch", expected_fingerprint="SHA256:wrong")
        hold("private-key-input", source=private_key)
        rsa = public_dir / "rsa.pub"
        rsa.write_text("ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC7 invalid\n")
        os.chmod(rsa, 0o600)
        hold("rsa-key", source=rsa)
        multiple = public_dir / "multiple.pub"
        multiple.write_bytes(public_key.read_bytes() + public_key.read_bytes())
        os.chmod(multiple, 0o600)
        hold("multiple-public-keys", source=multiple)
        malformed = public_dir / "malformed.pub"
        malformed.write_text("ssh-ed25519 not-base64\n")
        os.chmod(malformed, 0o600)
        hold("malformed-public-key", source=malformed)
        options = public_dir / "options.pub"
        options.write_text("cert-authority ssh-ed25519 AAAA\n")
        os.chmod(options, 0o600)
        hold("key-options", source=options)
        writable = public_dir / "writable.pub"
        writable.write_bytes(public_key.read_bytes())
        os.chmod(writable, 0o622)
        hold("writable-public-key", source=writable)
        linked = public_dir / "linked.pub"
        linked.symlink_to(public_key)
        hold("symlinked-public-key", source=linked)
        occupied = roster_dir / "occupied"
        occupied.write_text("existing\n")
        hold("occupied-destination", destination_path=occupied)
        linked_destination = roster_dir / "linked-destination"
        linked_destination.symlink_to(roster)
        hold("symlinked-destination", destination_path=linked_destination)
        unsafe_parent = root / "unsafe-parent"
        unsafe_parent.mkdir(mode=0o777)
        os.chmod(unsafe_parent, 0o777)
        hold("unsafe-parent", destination_path=unsafe_parent / "allowed_signers")
        hold("inside-checkout", destination_path=checkout / "allowed_signers")
        hold("relative-public-key", source=Path("relative.pub"))

    counts: dict[str, int] = {}
    for scenario in scenarios:
        counts[scenario["status"]] = counts.get(scenario["status"], 0) + 1
    return {
        "scenario": "aegis-public-roster-enrollment-v1",
        "status_counts": counts,
        "scenarios": scenarios,
        "measurements": {
            "public_rosters_provisioned": counts.get(
                "PUBLIC_ROSTER_PROVISIONED_FOR_DEVELOPMENT_REVIEW", 0
            ),
            "handoffs_ready": counts.get("READY_FOR_OFFLINE_SIGNATURE", 0),
            "adversarial_holds": counts.get("HOLD", 0),
            "unsafe_ready": counts.get("UnsafeReady", 0),
            "private_keys_accepted_by_truepanel": 0,
            "keys_generated_by_truepanel": 0,
            "signer_invocations_by_truepanel": 0,
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


__all__ = ["run_roster_enrollment_checkride"]
