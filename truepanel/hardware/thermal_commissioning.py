"""
Canonical thermal-control commissioning state.

This module converts low-level runtime flags into one stable operational
state for APIs, dashboards, logs, and future integrations.
"""


THERMAL_COMMISSIONING_STATES = (
    "configured",
    "dry_run_armed",
    "supervised_live",
    "commissioned_disarmed",
)


def thermal_commissioning_state(
    *,
    policy_mode,
    operator_armed,
    dry_run,
    supervised_session_active,
):
    """Return the canonical thermal commissioning state."""

    if bool(supervised_session_active):
        return "supervised_live"

    if bool(operator_armed) and bool(dry_run):
        return "dry_run_armed"

    if str(policy_mode) == "automatic_control":
        return "commissioned_disarmed"

    return "configured"


__all__ = [
    "THERMAL_COMMISSIONING_STATES",
    "thermal_commissioning_state",
]
