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
    if isinstance(reliability, dict) and reliability.get("project") == "AEGIS":
        airworthiness = reliability.get("airworthiness")
        if isinstance(airworthiness, dict) and airworthiness.get("status") == _AEGIS_STATUS:
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
    if isinstance(cards, list):
        blocked_smart_cards = [
            card for card in cards
            if isinstance(card, dict)
            and card.get("code") == _SMART_WARNING_CODE
            and isinstance(card.get("runtime"), dict)
            and isinstance(card["runtime"].get("action_gate"), dict)
            and card["runtime"]["action_gate"].get("physical_service_ready") is False
        ]
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
