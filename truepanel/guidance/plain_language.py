"""Vega-authored, deterministic plain-language explanations for existing alerts.

This is presentation text, not a detector, diagnostic, or service authority.
The underlying fault code, evidence, severity and TruePanel action gates remain
authoritative. No model, network call, background process, or disk I/O.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Final

from .catalog import guidance_codes


@dataclass(frozen=True)
class PlainLanguageAlert:
    code: str
    headline: str
    what_happened: str
    why_it_matters: str
    what_to_do: str
    do_not: str
    when_it_is_resolved: str


_PLAIN: Final[dict[str, PlainLanguageAlert]] = {
    "cooling.fan_stall": PlainLanguageAlert(
        "cooling.fan_stall",
        "A cooling fan may have stopped",
        "One of the monitored fans is spinning more slowly than expected or has stopped.",
        "The NAS may have less cooling available, even if temperatures look normal right now.",
        "Check the reported fan speed and temperatures. Make sure the outside vents are clear. If temperatures are rising, pause optional heavy jobs and arrange a review of the cooling system.",
        "Do not assume a normal temperature reading means the fan is working. Do not open the case or replace a fan without the correct service procedure.",
        "The monitored fan has returned to a stable speed and temperatures are no longer rising.",
    ),
    "thermal.high_temperature": PlainLanguageAlert(
        "thermal.high_temperature",
        "The NAS is getting too hot",
        "A monitored temperature has reached the system's configured high-temperature condition.",
        "Extended heat can affect system reliability. The alert alone does not establish whether workload, airflow, or a fan is responsible.",
        "Check the temperature trend and fan readings. Clear external airflow obstructions and pause optional heavy jobs while the cause is investigated.",
        "Do not change cooling controls or open the NAS based only on this message.",
        "The affected temperature has stayed below its configured recovery threshold and cooling readings are stable.",
    ),
    "storage.smart_warning": PlainLanguageAlert(
        "storage.smart_warning",
        "A drive is showing signs of trouble",
        "Drive-health monitoring has found a warning on a storage device. The storage pool may still say ONLINE.",
        "A drive can develop media errors before the pool reports that it has failed. This warning does not, by itself, prove that a particular physical bay is safe to service.",
        "Review the recorded drive-health evidence, check the pool's reported state, and verify the backup situation before planning service. Keep any physical-service HOLD in force.",
        "Do not remove or replace a drive based on its Linux device name, an unverified bay number, or a SMART PASSED label. Do not run extra drive tests or a scrub merely to confirm this message.",
        "The alert's triggering evidence has been reassessed and the relevant storage-health and recovery checks have been completed.",
    ),
    "storage.disk_faulted": PlainLanguageAlert(
        "storage.disk_faulted",
        "A storage drive has been marked as failed",
        "ZFS has marked a member of a storage pool as faulted.",
        "The pool may have less protection against another drive problem. The consequences depend on the affected pool and its layout.",
        "Review the exact affected pool and member, check independent backups, and follow the operator-approved recovery plan once physical identity and service prerequisites are verified.",
        "Do not pull a drive because a device path or bay number looks familiar. Do not remove another member, start a replacement, or force a storage operation while the relevant safety gates are on HOLD.",
        "The affected pool and member have passed the applicable recovery verification after any required repair.",
    ),
    "storage.pool_degraded": PlainLanguageAlert(
        "storage.pool_degraded",
        "A storage pool has reduced protection",
        "One or more parts of a storage pool are not healthy. The pool may still be accessible.",
        "A further problem could affect access to data. The risk depends on the actual member state and pool layout.",
        "Review the pool and member details, confirm backup status, and check whether recovery is already in progress. Follow the member-specific guidance once its cause is established.",
        "Do not guess which drive to remove, start another repair during recovery, or treat a reachable pool as fully healthy.",
        "The affected pool has returned to its expected healthy state and any required recovery has finished.",
    ),
    "network.link_down": PlainLanguageAlert(
        "network.link_down",
        "A network connection has dropped",
        "A monitored Ethernet port is no longer reporting a working physical link.",
        "Some devices may be unable to reach the NAS. Another network port or management path may still work.",
        "If you still have access, keep that connection available. Check the affected cable and the connected switch or router port before changing settings.",
        "Do not disconnect your only working management connection or assume the NAS itself has failed.",
        "The affected port reports a working link and the expected network address is available again.",
    ),
    "front_panel.lcd_unavailable": PlainLanguageAlert(
        "front_panel.lcd_unavailable",
        "The front display is not responding",
        "TruePanel is having trouble communicating with the NAS's front-panel LCD controller.",
        "This affects the front display and does not, on its own, mean that the storage pool or NAS has failed.",
        "Check whether Mission Control is still accessible. Review the LCD connection and service status; try the narrowest approved TruePanel service recovery if needed.",
        "Do not reboot the NAS or open the chassis just because the display is unavailable.",
        "The controller is communicating again and the display reader and dispatcher are healthy.",
    ),
    "telemetry.stale": PlainLanguageAlert(
        "telemetry.stale",
        "TruePanel cannot trust its latest readings",
        "Some hardware readings have stopped updating recently enough for normal automated decisions.",
        "An old reading can look normal even while the real hardware condition has changed.",
        "Use the displayed source and age details to find the missing readings. Keep applicable safety holds in place and restore the narrowest affected telemetry source.",
        "Do not treat an old temperature, fan speed, or device reading as proof that everything is healthy. Do not bypass a safety HOLD.",
        "The required readings are updating consistently again and their safety checks have been reevaluated.",
    ),
}


def plain_language_for_card(card: dict[str, Any]) -> dict[str, Any]:
    """Return an additive safe copy for a currently detected guidance card.

    Unknown codes never get a fabricated diagnosis. Output never claims an
    operator acknowledged backups or that service readiness has been granted.
    """

    if not isinstance(card, dict):
        raise ValueError("Guidance card must be a mapping")
    code = card.get("code")
    if not isinstance(code, str) or code not in _PLAIN:
        raise ValueError("No plain-language explanation for guidance code")

    payload = asdict(_PLAIN[code])
    runtime = card.get("runtime")
    gate = runtime.get("action_gate") if isinstance(runtime, dict) else None
    physical_ready = (
        gate.get("physical_service_ready") is True
        if isinstance(gate, dict) else False
    )
    destructive_ready = (
        gate.get("destructive_actions_ready") is True
        if isinstance(gate, dict) else False
    )
    payload["physical_service_ready"] = physical_ready
    payload["destructive_actions_ready"] = destructive_ready
    payload["authorization_granted"] = False
    payload["explanation_source"] = "DETERMINISTIC_CATALOG"
    payload["runtime_model_required"] = False

    if code == "storage.smart_warning":
        evidence = runtime.get("evidence") if isinstance(runtime, dict) else None
        severity = card.get("severity")
        if severity == "critical":
            payload["headline"] = "A drive has serious signs of failure"
            payload["why_it_matters"] = (
                "Critical drive-health evidence can signal active media damage "
                "even when the drive self-check says PASSED and the pool says ONLINE. "
                "A physical replacement must still follow verified identity, "
                "backup review, and the applicable service HOLD."
            )
        if not isinstance(evidence, dict) or not evidence.get("bay"):
            payload["what_to_do"] += (
                " The exact physical bay has not been established by this explanation."
            )

    if not physical_ready and code.startswith("storage."):
        payload["do_not"] += (
            " Physical service is not ready according to the current action gate."
        )
    if code.startswith("storage.") and not destructive_ready:
        payload["do_not"] += " Storage-changing actions are not authorized here."

    return payload


def plain_language_codes() -> tuple[str, ...]:
    return tuple(_PLAIN)


if set(_PLAIN) != set(guidance_codes()):
    raise RuntimeError("Plain-language catalogue must cover every guidance code")


__all__ = ["PlainLanguageAlert", "plain_language_codes", "plain_language_for_card"]
