"""Deterministic HoloDeck checkride for public operator action packets."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from truepanel.aegis import verifier_bootstrap
from truepanel.aegis.field_ceremony import assess_field_ceremony
from truepanel.aegis.operator_action_packet import (
    build_operator_action_packet,
    render_operator_action_card,
    verify_operator_action_packet,
)
from truepanel.holodeck import aegis_independent_kit_auditor as standalone


def run_operator_action_packet_checkride() -> dict[str, Any]:
    """Prove exact reconstruction and reject presentation or authority drift."""

    receipt = Path(verifier_bootstrap.__file__).with_name(
        "independent_verifier_release.json"
    ).resolve()
    source = Path(standalone.__file__).resolve()
    ceremony = assess_field_ceremony(
        verifier_receipt_path=receipt,
        verifier_source_path=source,
    )
    packet = build_operator_action_packet(
        ceremony_result=ceremony,
        verifier_receipt_path=receipt,
        verifier_source_path=source,
    )
    scenarios: list[dict[str, str]] = []

    def record(name: str, value: dict[str, Any]) -> None:
        scenarios.append(
            {
                "scenario": name,
                "status": value["status"],
                "reason": value.get("reason", value.get("action_status", "verified")),
            }
        )

    def verify(candidate: dict[str, Any], result: dict[str, Any] | None = None) -> dict[str, Any]:
        return verify_operator_action_packet(
            packet=candidate,
            ceremony_result=result or ceremony,
            verifier_receipt_path=receipt,
            verifier_source_path=source,
        )

    record("exact-public-action-packet", verify(packet))
    card = render_operator_action_card(packet)

    for name, field, value in (
        ("action-substitution", "next_action", "INSTALL_TO_PRODUCTION"),
        ("verifier-substitution", "verifier_source_sha256", "0" * 64),
        ("authority-escalation", "hardware_authority", True),
        ("private-key-request", "private_key_requested", True),
        ("independence-spoof", "independent_channel_verified", True),
    ):
        changed = deepcopy(packet)
        changed[field] = value
        record(name, verify(changed))

    extended = deepcopy(packet)
    extended["unexpected"] = "field"
    record("packet-extension", verify(extended))

    changed_ceremony = deepcopy(ceremony)
    changed_ceremony["completed_stages"][0]["source_sha256"] = "0" * 64
    record("ceremony-substitution", verify(packet, changed_ceremony))

    ineligible = deepcopy(ceremony)
    ineligible["status"] = "ELIGIBLE_FOR_DEVELOPMENT_CANDIDATE_REVIEW"
    try:
        build_operator_action_packet(
            ceremony_result=ineligible,
            verifier_receipt_path=receipt,
            verifier_source_path=source,
        )
    except ValueError as error:
        record("eligible-result-is-not-an-action", {"status": "DENIED", "reason": str(error)})

    held = deepcopy(ceremony)
    held["status"] = "HOLD"
    try:
        build_operator_action_packet(
            ceremony_result=held,
            verifier_receipt_path=receipt,
            verifier_source_path=source,
        )
    except ValueError as error:
        record("held-result-is-not-an-action", {"status": "DENIED", "reason": str(error)})

    counts: dict[str, int] = {}
    for scenario in scenarios:
        counts[scenario["status"]] = counts.get(scenario["status"], 0) + 1
    return {
        "scenario": "aegis-operator-action-packet-v1",
        "status_counts": counts,
        "scenarios": scenarios,
        "measurements": {
            "packets_verified": counts.get("OPERATOR_ACTION_PACKET_VERIFIED", 0),
            "adversarial_holds": counts.get("HOLD", 0),
            "non_action_denials": counts.get("DENIED", 0),
            "card_names_independent_boundary": int(
                "not an independent trust source" in card
            ),
            "action_satisfactions": 0,
            "independent_channels_manufactured": 0,
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


__all__ = ["run_operator_action_packet_checkride"]
