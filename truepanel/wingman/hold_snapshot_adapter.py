"""Read-only, lab-only adapter for TruePanel's structured HOLD status fields.

The *caller*, not this function, is responsible for supplying an internal,
trusted, current server-composed snapshot. Never call with a client POST body,
model response, retrieved document, or historical recording as live authority.
This adapter is not connected to the Mission Control production request path.
"""

from __future__ import annotations

from typing import Any

from .current_identity_witness import CurrentDriveWitness
from .hold_envelope import HoldEvidence, HoldKind

_SMART_WARNING_CODE = "storage.smart_warning"
_AEGIS_STATUS = "HOLD"


_CURRENT_IDENTITY_PROOFS = {
    ("wwn", "udev_wwn_cross_checked_inventory"),
    ("serial_model", "inventory_serial_cross_checked"),
}


def _verified_current_bay(
    card: dict[str, Any],
    lifeline: Any,
    witness: CurrentDriveWitness | None = None,
) -> int | None:
    """Require a unique active Lifeline session AND independent hardware proof.

    Runtime Linux names, a guidance-card bay, a stored fingerprint count, a
    high-confidence ZFS member identity, and an operator acknowledgement are
    never sufficient on their own. All observable identity fields must agree.
    """

    runtime = card.get("runtime")
    evidence = runtime.get("evidence") if isinstance(runtime, dict) else None
    if not isinstance(evidence, dict) or not isinstance(lifeline, dict):
        return None
    sessions = lifeline.get("sessions")
    if not isinstance(sessions, list):
        return None
    if witness is not None and type(witness) is not CurrentDriveWitness:
        return None
    pool = evidence.get("pool")
    vdev = evidence.get("vdev")
    device = evidence.get("device")
    suffix = evidence.get("serial_last4")
    bay = evidence.get("bay")
    member = evidence.get("member_id")
    if (
        not all(isinstance(value, str) and value.strip()
                for value in (pool, vdev, device, suffix))
        or type(bay) is not int
        or not 1 <= bay <= 999
    ):
        return None

    matches: list[dict[str, Any]] = []
    for session in sessions:
        if not isinstance(session, dict):
            continue
        original = session.get("original_fault")
        identity = session.get("drive_identity")
        repair = session.get("last_session")
        if not all(isinstance(item, dict)
                   for item in (original, identity, repair)):
            continue
        target = repair.get("target")
        if not isinstance(target, dict):
            continue
        if (
            session.get("status") != "active"
            or session.get("trigger_code") != _SMART_WARNING_CODE
            or (identity.get("mode"), identity.get("source"))
            not in _CURRENT_IDENTITY_PROOFS
            or identity.get("confidence") not in {"high", "very_high"}
            or not isinstance(identity.get("stable_key"), str)
            or not identity["stable_key"].strip()
        ):
            continue
        # Require a current independently observed mapping, not historical
        # provenance and not a stored ZFS-only identity. Every available
        # member ID must agree, but do not use a Linux path as member proof.
        if member and (
            not isinstance(member, str)
            or original.get("member_id") != member
            or target.get("member_id") != member
        ):
            continue
        if any(record.get("pool") != pool or record.get("vdev") != vdev
               for record in (original, target)):
            continue
        if any(record.get("device") != device
               for record in (original, target, identity)):
            continue
        if any(record.get("bay") != bay
               for record in (original, target, identity)):
            continue
        if (
            original.get("serial_last4") != suffix
            or identity.get("serial_last4") != suffix
        ):
            continue
        gates = repair.get("gates")
        if not isinstance(gates, list) or not any(
            isinstance(gate, dict)
            and gate.get("code") == "physical_identity"
            and gate.get("satisfied") is True
            for gate in gates
        ):
            continue
        matches.append(session)

    # The independent current witness must corroborate the complete matched
    # identity; a last-known-good ledger on its own cannot name a live bay.
    if len(matches) != 1 or witness is None:
        return None
    identity = matches[0]["drive_identity"]
    return bay if all((
        witness.pool == pool,
        witness.vdev == vdev,
        witness.member_id == member,
        witness.device == device,
        witness.bay == bay,
        witness.serial_last4 == suffix,
        witness.stable_key == identity["stable_key"],
        witness.mode == identity["mode"],
        witness.source == identity["source"],
        witness.confidence == identity["confidence"],
    )) else None


def holds_from_trusted_snapshot(
    snapshot: dict[str, Any],
    *,
    current_identity_witness: CurrentDriveWitness | None = None,
) -> tuple[HoldEvidence, ...]:
    """Map only confirmed structured action gates, never natural-language prose.

    For storage, the operator guidance runtime gate establishes that physical
    service is not ready. The card's bay is *not* sufficient to claim verified
    physical identity, so this stage publishes an unlocalized HOLD. A later
    independently verified Lifeline join may resolve it to a specific bay.
    """

    if not isinstance(snapshot, dict):
        raise ValueError("Trusted snapshot must be a mapping")

    holds: list[HoldEvidence] = []

    reliability = snapshot.get("reliability")
    if not isinstance(reliability, dict) or reliability.get("project") != "AEGIS":
        raise ValueError("AEGIS reliability evidence unavailable or untrusted")
    airworthiness = reliability.get("airworthiness")
    if not isinstance(airworthiness, dict):
        raise ValueError("AEGIS airworthiness evidence unavailable")
    aegis_status = airworthiness.get("status")
    if aegis_status not in {_AEGIS_STATUS, "CURRENT"}:
        # REVIEW, UNKNOWN, and unexpected states must not become 'no HOLD'.
        raise ValueError("AEGIS status is not resolved for the HOLD adapter")
    if aegis_status == _AEGIS_STATUS:
        reason = airworthiness.get("reason")
        if not isinstance(reason, str) or not reason:
            reason = "ReasonUnavailable"
        holds.append(
            HoldEvidence(
                kind=HoldKind.AEGIS_AIRWORTHINESS,
                reason_code=reason,
                source_id="status:reliability",
            )
        )

    cards = snapshot.get("operator_guidance")
    if not isinstance(cards, list):
        raise ValueError("Operator guidance evidence unavailable")
    blocked_smart_cards: list[dict[str, Any]] = []
    for card in cards:
        if not isinstance(card, dict):
            raise ValueError("Malformed operator guidance card")
        if card.get("code") != _SMART_WARNING_CODE:
            continue
        runtime = card.get("runtime")
        gate = runtime.get("action_gate") if isinstance(runtime, dict) else None
        if not isinstance(gate, dict) or type(gate.get("physical_service_ready")) is not bool:
            raise ValueError("SMART physical service readiness unknown")
        if gate["physical_service_ready"] is False:
            blocked_smart_cards.append(card)
    if blocked_smart_cards:
        # Multiple blocked cards or any unresolved identity stay unlocalized.
        bay = (
            _verified_current_bay(
                blocked_smart_cards[0],
                snapshot.get("lifeline"),
                current_identity_witness,
            )
            if len(blocked_smart_cards) == 1 else None
        )
        holds.append(
            HoldEvidence(
                kind=(
                    HoldKind.PHYSICAL_SERVICE if bay is not None
                    else HoldKind.PHYSICAL_SERVICE_UNLOCALIZED
                ),
                reason_code="ServiceNotReady",
                source_id="status:operator_guidance",
                bay=bay,
            )
        )

    return tuple(holds)


__all__ = ["holds_from_trusted_snapshot"]
