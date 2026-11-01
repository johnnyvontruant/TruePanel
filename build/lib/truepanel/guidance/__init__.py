"""Mission Control operator-guidance primitives."""

from .catalog import (
    FaultGuidance,
    GuidanceSource,
    GuidanceStep,
    HOLODECK_MISSION_GUIDANCE,
    guidance_codes,
    guidance_for,
    guidance_for_mission,
    guidance_payload,
)
from .recovery import (
    RECOVERY_SCHEMA_VERSION,
    decorate_guidance,
    recovery_contract,
    transition_recovery,
    verification_for_card,
)
from .runtime import guidance_for_snapshot as _runtime_guidance_for_snapshot
from .thermal import thermal_guidance_for_snapshot


def guidance_for_snapshot(payload):
    """Return live guidance decorated with Pathfinder recovery contracts."""

    cards = _runtime_guidance_for_snapshot(payload)
    cards.extend(thermal_guidance_for_snapshot(payload))
    return decorate_guidance(cards)


__all__ = [
    "FaultGuidance",
    "GuidanceSource",
    "GuidanceStep",
    "HOLODECK_MISSION_GUIDANCE",
    "RECOVERY_SCHEMA_VERSION",
    "decorate_guidance",
    "guidance_codes",
    "guidance_for",
    "guidance_for_mission",
    "guidance_for_snapshot",
    "guidance_payload",
    "recovery_contract",
    "thermal_guidance_for_snapshot",
    "transition_recovery",
    "verification_for_card",
]
