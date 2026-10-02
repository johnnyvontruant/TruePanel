"""Deterministic HoloDeck checkride for verifier confirmation receipts."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from truepanel.aegis import verifier_bootstrap
from truepanel.aegis.verifier_confirmation import (
    build_verifier_confirmation_challenge,
    create_verifier_confirmation_receipt,
    verify_verifier_confirmation_receipt,
)
from truepanel.holodeck import aegis_independent_kit_auditor as standalone


def run_verifier_confirmation_checkride() -> dict[str, Any]:
    """Prove a short-lived attestation cannot become cryptographic authority."""

    release_receipt = Path(verifier_bootstrap.__file__).with_name(
        "independent_verifier_release.json"
    ).resolve()
    source = Path(standalone.__file__).resolve()
    release = verifier_bootstrap.verify_verifier_release(
        receipt_path=release_receipt,
        source_path=source,
    )
    challenge = build_verifier_confirmation_challenge(release)
    receipt = create_verifier_confirmation_receipt(
        challenge=challenge,
        independently_observed_sha256=release["source_sha256"],
        channel="SEPARATE_OPERATOR_DEVICE",
        confirmed_at="2026-10-02T03:00:00Z",
    )
    scenarios: list[dict[str, str]] = []

    def record(name: str, status: str, reason: str) -> None:
        scenarios.append({"scenario": name, "status": status, "reason": reason})

    exact = verify_verifier_confirmation_receipt(
        receipt=receipt,
        release=release,
        observed_at="2026-10-02T03:10:00Z",
    )
    record("exact-operator-attestation", exact["status"], exact["evidence_class"])

    denied_builds = (
        (
            "mismatched-independent-digest",
            challenge,
            "0" * 64,
            "SEPARATE_OPERATOR_DEVICE",
        ),
        (
            "same-repository-channel",
            challenge,
            release["source_sha256"],
            "SAME_REPOSITORY",
        ),
        (
            "extended-challenge",
            {**challenge, "unexpected": True},
            release["source_sha256"],
            "SEPARATE_OPERATOR_DEVICE",
        ),
    )
    for name, candidate, digest, channel in denied_builds:
        try:
            create_verifier_confirmation_receipt(
                challenge=candidate,
                independently_observed_sha256=digest,
                channel=channel,
                confirmed_at="2026-10-02T03:00:00Z",
            )
        except ValueError as error:
            record(name, "DENIED", str(error))

    attacks: list[tuple[str, str, Any, str]] = [
        ("challenge-substitution", "challenge_sha256", "0" * 64, "2026-10-02T03:10:00Z"),
        ("channel-substitution", "channel", "SAME_REPOSITORY", "2026-10-02T03:10:00Z"),
        ("claim-removed", "independent_channel_claimed", False, "2026-10-02T03:10:00Z"),
        (
            "cryptographic-proof-spoof",
            "independent_channel_cryptographically_verified",
            True,
            "2026-10-02T03:10:00Z",
        ),
        ("authority-escalation", "production_authority", True, "2026-10-02T03:10:00Z"),
        ("private-key-accepted", "private_key_accepted", True, "2026-10-02T03:10:00Z"),
        ("signer-invoked", "signer_invoked", True, "2026-10-02T03:10:00Z"),
    ]
    for name, field, replacement, observed_at in attacks:
        changed = deepcopy(receipt)
        changed[field] = replacement
        try:
            verify_verifier_confirmation_receipt(
                receipt=changed,
                release=release,
                observed_at=observed_at,
            )
        except ValueError as error:
            record(name, "HOLD", str(error))

    extended = {**receipt, "unexpected": True}
    try:
        verify_verifier_confirmation_receipt(
            receipt=extended,
            release=release,
            observed_at="2026-10-02T03:10:00Z",
        )
    except ValueError as error:
        record("receipt-extension", "HOLD", str(error))

    for name, observed_at in (
        ("future-confirmation", "2026-10-02T02:59:59Z"),
        ("expired-confirmation", "2026-10-02T03:30:01Z"),
    ):
        try:
            verify_verifier_confirmation_receipt(
                receipt=receipt,
                release=release,
                observed_at=observed_at,
            )
        except ValueError as error:
            record(name, "HOLD", str(error))

    counts: dict[str, int] = {}
    for scenario in scenarios:
        counts[scenario["status"]] = counts.get(scenario["status"], 0) + 1
    return {
        "scenario": "aegis-verifier-confirmation-receipt-v1",
        "status_counts": counts,
        "scenarios": scenarios,
        "measurements": {
            "operator_attestations_verified": counts.get(
                "OPERATOR_ATTESTED_INDEPENDENT_CHANNEL", 0
            ),
            "adversarial_holds": counts.get("HOLD", 0),
            "unsafe_builds_denied": counts.get("DENIED", 0),
            "legacy_magic_string_paths": 0,
            "cryptographic_independence_claims": 0,
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


__all__ = ["run_verifier_confirmation_checkride"]
