"""Read-only, lab-only adapter for TruePanel's structured HOLD status fields.

The *caller*, not this function, is responsible for supplying an internal,
trusted, current server-composed snapshot. Never call with a client POST body,
model response, retrieved document, or historical recording as live authority.
This adapter is not connected to the Mission Control production request path.
"""

from __future__ import annotations

from typing import Any

from .hold_envelope import HoldEvidence, HoldKind

_SMART_WARNING_CODE = "storage.smart_warning"
_AEGIS_STATUS = "HOLD"


def holds_from_trusted_snapshot(
    snapshot: dict[str, Any],
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
    blocked_smart_cards = False
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
            blocked_smart_cards = True
    if blocked_smart_cards:
        holds.append(
            HoldEvidence(
                kind=HoldKind.PHYSICAL_SERVICE_UNLOCALIZED,
                reason_code="ServiceNotReady",
                source_id="status:operator_guidance",
            )
        )

    return tuple(holds)


__all__ = ["holds_from_trusted_snapshot"]
