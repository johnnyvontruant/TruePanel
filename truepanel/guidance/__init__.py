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
    verification_for_card,
)
from .runtime import guidance_for_snapshot as _runtime_guidance_for_snapshot


def guidance_for_snapshot(payload):
    """Return live guidance decorated with Pathfinder recovery contracts."""

    return decorate_guidance(_runtime_guidance_for_snapshot(payload))


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
    "verification_for_card",
]
