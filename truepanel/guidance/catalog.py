"""Operator guidance catalog for Mission Control fault recovery.

The catalog is intentionally data-first. Fault detection stays in the existing
health/watchers stack; this module describes what Mission Control should tell
an operator after a fault has already been identified.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Final


@dataclass(frozen=True)
class GuidanceSource:
    title: str
    url: str
    authority: str
    scope: str


@dataclass(frozen=True)
class GuidanceStep:
    title: str
    detail: str
    risk: str = "safe"
    requires_shutdown: bool = False
    destructive: bool = False


@dataclass(frozen=True)
class FaultGuidance:
    code: str
    title: str
    severity: str
    summary: str
    evidence_fields: tuple[str, ...]
    immediate_actions: tuple[GuidanceStep, ...]
    diagnosis: tuple[GuidanceStep, ...]
    remediation: tuple[GuidanceStep, ...]
    verification: tuple[GuidanceStep, ...]
    escalation: str
    model_specific: bool
    sources: tuple[GuidanceSource, ...]


TRUENAS_DHM: Final = GuidanceSource(
    title="TrueNAS 25.10 Drive Health Management",
    url=(
        "https://www.truenas.com/docs/scale/25.10/scaletutorials/"
        "scaletutorialsprint/#drive-health-management"
    ),
    authority="TrueNAS",
    scope="SMART polling, ZFS failure detection, drive-health alerts",
)
TRUENAS_POOLS: Final = GuidanceSource(
    title="TrueNAS 25.10 Managing Pools",
    url=(
        "https://www.truenas.com/docs/scale/25.10/scaletutorials/storage/"
        "managepoolsscale/"
    ),
    authority="TrueNAS",
    scope="offline, replace, resilver, pool recovery",
)
TRUENAS_POOL_REPLACE_API: Final = GuidanceSource(
    title="TrueNAS API v25.10.4 pool.replace",
    url="https://api.truenas.com/v25.10/api_methods_pool.replace.html",
    authority="TrueNAS",
    scope="replacement semantics and force option",
)
QNAP_TVS_X71_MANUAL: Final = GuidanceSource(
    title="QNAP TVS-x71 Series Hardware User Manual",
    url=(
        "https://download.qnap.com/TechnicalDocument/"
        "QNAP_TVS-x71-QNAP_Turbo_NAS_Hardware_Manual_ENG_20150330.pdf"
    ),
    authority="QNAP",
    scope="TVS-471/671/871 chassis safety and hot-swap guidance",
)


_CATALOG: Final[dict[str, FaultGuidance]] = {
    "cooling.fan_stall": FaultGuidance(
        code="cooling.fan_stall",
        title="Cooling fan stopped or below safe RPM",
        severity="warning",
        summary=(
            "A monitored chassis fan is not rotating at the expected speed. "
            "Cooling redundancy may be reduced even if temperatures are still normal."
        ),
        evidence_fields=(
            "fan_label",
            "fan_channel",
            "current_rpm",
            "expected_rpm_range",
            "failure_observations",
            "other_fan_rpm",
            "cpu_temperature_c",
            "system_temperature_c",
            "telemetry_age_seconds",
        ),
        immediate_actions=(
            GuidanceStep(
                "Confirm temperatures are stable",
                "Check current CPU/system temperatures and whether another monitored fan remains healthy.",
            ),
            GuidanceStep(
                "Reduce thermal load if temperatures are rising",
                "Pause nonessential heavy workloads while the cooling fault is investigated.",
            ),
        ),
        diagnosis=(
            GuidanceStep(
                "Distinguish a fan stall from missing telemetry",
                "Verify that the fan RPM channel is present and other hardware-monitor readings remain current.",
            ),
            GuidanceStep(
                "Inspect external airflow",
                "Check that vents are clear and listen for scraping, pulsing, or a stopped fan without opening the chassis.",
            ),
        ),
        remediation=(
            GuidanceStep(
                "Use the model-specific service procedure",
                "If the fan remains stopped, follow the chassis manual or qualified service procedure before opening the NAS.",
                risk="caution",
                requires_shutdown=True,
            ),
        ),
        verification=(
            GuidanceStep(
                "Verify fan recovery",
                "Confirm stable RPM above the configured minimum for multiple observations and confirm temperatures are not rising.",
            ),
        ),
        escalation=(
            "Escalate immediately if all chassis fans stop, temperature rises rapidly, "
            "or the hardware manual does not classify the fan as user-serviceable."
        ),
        model_specific=True,
        sources=(QNAP_TVS_X71_MANUAL,),
    ),
    "thermal.high_temperature": FaultGuidance(
        code="thermal.high_temperature",
        title="System temperature above normal operating range",
        severity="warning",
        summary=(
            "One or more monitored temperatures are elevated. The cause can be workload, "
            "restricted airflow, fan degradation, dust accumulation, or ambient temperature."
        ),
        evidence_fields=(
            "sensor_label",
            "current_temperature_c",
            "recent_peak_c",
            "temperature_trend",
            "fan_rpm",
            "ambient_context",
        ),
        immediate_actions=(
            GuidanceStep(
                "Reduce avoidable workload",
                "Pause optional high-load jobs and watch whether the temperature trend stabilizes.",
            ),
            GuidanceStep(
                "Check ventilation",
                "Confirm the NAS has unobstructed intake/exhaust space and is not exposed to an unusually hot environment.",
            ),
        ),
        diagnosis=(
            GuidanceStep(
                "Correlate fans and temperature",
                "Compare fan RPM, fan alarms, and the temperature trend to determine whether cooling capacity has changed.",
            ),
        ),
        remediation=(
            GuidanceStep(
                "Correct the cooling cause",
                "Restore failed cooling or airflow before returning the system to sustained heavy load.",
                risk="caution",
            ),
        ),
        verification=(
            GuidanceStep(
                "Confirm thermal recovery",
                "Require the temperature to return below the configured recovery threshold and remain stable before clearing the guidance card.",
            ),
        ),
        escalation=(
            "Escalate if temperature continues rising despite reduced load, if fan faults coexist, "
            "or if the chassis exceeds the manufacturer's operating-temperature guidance."
        ),
        model_specific=True,
        sources=(QNAP_TVS_X71_MANUAL,),
    ),
    "storage.smart_warning": FaultGuidance(
        code="storage.smart_warning",
        title="Drive-health warning detected",
        severity="caution",
        summary=(
            "TrueNAS drive-health monitoring reported a SMART condition that can indicate "
            "degradation. A SMART warning is not identical to a ZFS FAULTED device."
        ),
        evidence_fields=(
            "pool",
            "vdev",
            "bay",
            "device",
            "model",
            "serial_last4",
            "smart_attribute",
            "smart_value",
            "zfs_state",
            "read_errors",
            "write_errors",
            "checksum_errors",
        ),
        immediate_actions=(
            GuidanceStep(
                "Confirm backup health",
                "Verify that important data has a current independent backup before taking storage-repair actions.",
            ),
            GuidanceStep(
                "Check ZFS state separately",
                "Determine whether the device and pool are still ONLINE, DEGRADED, or FAULTED before recommending replacement urgency.",
            ),
        ),
        diagnosis=(
            GuidanceStep(
                "Review the triggering health evidence",
                "Show the SMART attribute/event alongside ZFS read, write, and checksum errors instead of collapsing them into one generic disk fault.",
            ),
            GuidanceStep(
                "Identify the physical drive",
                "Map the TrueNAS disk identity to the enclosure bay before any physical action is suggested.",
            ),
        ),
        remediation=(
            GuidanceStep(
                "Prepare a replacement when degradation is credible",
                "Use a replacement disk with capacity equal to or greater than the failing disk and validate that it is not a member of another pool.",
                risk="caution",
            ),
        ),
        verification=(
            GuidanceStep(
                "Verify health after intervention",
                "Confirm the pool state, disk-health alerts, and error counters after replacement or continued observation.",
            ),
        ),
        escalation=(
            "Escalate to replacement guidance when TrueNAS marks the device FAULTED, ZFS errors accumulate, "
            "or the drive-health alert explicitly recommends replacement."
        ),
        model_specific=False,
        sources=(TRUENAS_DHM, TRUENAS_POOLS),
    ),
    "storage.disk_faulted": FaultGuidance(
        code="storage.disk_faulted",
        title="Pool member faulted",
        severity="warning",
        summary=(
            "ZFS has faulted a storage device. Redundancy can be reduced and a second failure "
            "may place data at greater risk depending on VDEV topology."
        ),
        evidence_fields=(
            "pool",
            "vdev",
            "vdev_topology",
            "remaining_redundancy",
            "bay",
            "device",
            "model",
            "capacity_bytes",
            "present",
            "zfs_state",
            "read_errors",
            "write_errors",
            "checksum_errors",
        ),
        immediate_actions=(
            GuidanceStep(
                "Protect remaining redundancy",
                "Do not remove another member of the affected VDEV while redundancy is reduced.",
            ),
            GuidanceStep(
                "Verify backups",
                "Confirm current backups before beginning a replacement workflow.",
            ),
            GuidanceStep(
                "Identify the exact bay",
                "Use enclosure mapping and, where safely supported, the bay identify LED before physical removal.",
            ),
        ),
        diagnosis=(
            GuidanceStep(
                "Confirm the failed member",
                "Show pool, VDEV, ZFS device state, physical bay, serial suffix, and error counters together.",
            ),
            GuidanceStep(
                "Check replacement constraints",
                "The replacement must be the same capacity or larger and must not contain data that the operator intends to preserve.",
            ),
        ),
        remediation=(
            GuidanceStep(
                "Offline the failed member when required",
                "Use the TrueNAS storage workflow to offline the correct member before same-slot removal when the failed device is still present.",
                risk="caution",
            ),
            GuidanceStep(
                "Replace the physical disk",
                "Follow the chassis-specific hot-swap or shutdown procedure for the detected hardware model.",
                risk="caution",
                requires_shutdown=False,
            ),
            GuidanceStep(
                "Start the TrueNAS replacement",
                "Select the intended replacement disk and begin replacement. Do not use Force unless the operator explicitly accepts destruction of data on the selected replacement disk.",
                risk="destructive",
                destructive=True,
            ),
        ),
        verification=(
            GuidanceStep(
                "Monitor resilver",
                "Confirm replacement starts, surface resilver progress, and prohibit another member replacement until recovery completes.",
            ),
            GuidanceStep(
                "Confirm redundancy restored",
                "Clear the repair guidance only after the VDEV/pool returns to the expected healthy state and the replacement device is ONLINE.",
            ),
        ),
        escalation=(
            "Escalate if more devices are degraded than the VDEV can safely tolerate, the pool becomes unavailable, "
            "the replacement candidate is ambiguous, or the chassis procedure is not verified for the model."
        ),
        model_specific=True,
        sources=(TRUENAS_POOLS, TRUENAS_POOL_REPLACE_API, QNAP_TVS_X71_MANUAL),
    ),
    "storage.pool_degraded": FaultGuidance(
        code="storage.pool_degraded",
        title="Storage pool degraded",
        severity="warning",
        summary=(
            "The pool remains available but one or more components are not healthy. "
            "The safe repair path depends on the exact VDEV topology and affected member state."
        ),
        evidence_fields=(
            "pool",
            "pool_state",
            "affected_vdevs",
            "vdev_topology",
            "remaining_redundancy",
            "resilver_state",
            "affected_bays",
        ),
        immediate_actions=(
            GuidanceStep(
                "Do not guess which disk to pull",
                "Resolve the degraded VDEV to exact device and bay identities before suggesting physical removal.",
            ),
            GuidanceStep(
                "Check whether a resilver is already running",
                "If recovery is in progress, show progress and avoid starting conflicting storage work.",
            ),
        ),
        diagnosis=(
            GuidanceStep(
                "Expand the degradation tree",
                "Show which pool, VDEV, and member caused the DEGRADED state and whether the member is faulted, missing, or offline.",
            ),
        ),
        remediation=(
            GuidanceStep(
                "Route to the member-specific repair",
                "Use the exact underlying condition to select disk-fault, missing-disk, cable/path, or resilver guidance.",
                risk="caution",
            ),
        ),
        verification=(
            GuidanceStep(
                "Verify pool ONLINE",
                "Require the affected pool and repaired VDEV to return to ONLINE after any resilver or reinsertion completes.",
            ),
        ),
        escalation=(
            "Escalate when degradation affects multiple members, redundancy is exhausted, or the pool is no longer accessible."
        ),
        model_specific=False,
        sources=(TRUENAS_POOLS,),
    ),
    "network.link_down": FaultGuidance(
        code="network.link_down",
        title="Network interface link lost",
        severity="caution",
        summary=(
            "A monitored Ethernet interface no longer has carrier. The NAS may still be reachable through another interface or Tailscale."
        ),
        evidence_fields=(
            "interface",
            "label",
            "link_up",
            "operstate",
            "address",
            "primary",
            "other_reachable_interfaces",
            "tailscale_reachable",
        ),
        immediate_actions=(
            GuidanceStep(
                "Preserve alternate access",
                "If another management path is working, keep it connected while diagnosing the failed link.",
            ),
            GuidanceStep(
                "Check the physical path",
                "Verify the Ethernet cable is seated at both ends and inspect switch/router port link indicators.",
            ),
        ),
        diagnosis=(
            GuidanceStep(
                "Separate carrier loss from IP loss",
                "Show carrier/operstate independently from DHCP/static address state so the operator checks the right layer first.",
            ),
            GuidanceStep(
                "Check peer port and cable",
                "Try a known-good cable and a known-good peer port before assuming the NAS NIC has failed.",
            ),
        ),
        remediation=(
            GuidanceStep(
                "Restore the failed layer",
                "Replace or reseat the cable, correct the peer port, or restore network configuration based on the observed failure layer.",
            ),
        ),
        verification=(
            GuidanceStep(
                "Verify link and address recovery",
                "Confirm carrier is up, the expected IP returns, and Mission Control can observe traffic again.",
            ),
        ),
        escalation=(
            "Escalate to NIC or switch diagnostics if the interface stays down with a known-good cable and known-good peer port."
        ),
        model_specific=False,
        sources=(),
    ),
    "front_panel.lcd_unavailable": FaultGuidance(
        code="front_panel.lcd_unavailable",
        title="Front-panel LCD controller unavailable",
        severity="advisory",
        summary=(
            "TruePanel cannot currently communicate with the front-panel LCD controller. "
            "This should not be treated as a storage fault."
        ),
        evidence_fields=(
            "serial_device",
            "reader_connected",
            "last_successful_io",
            "dispatcher_alive",
            "mission_control_reachable",
        ),
        immediate_actions=(
            GuidanceStep(
                "Keep managing the NAS through Mission Control",
                "Confirm the web/host path remains healthy before troubleshooting the front panel.",
            ),
        ),
        diagnosis=(
            GuidanceStep(
                "Check controller path",
                "Verify the configured serial device exists and distinguish a missing device from a timeout or malformed response.",
            ),
        ),
        remediation=(
            GuidanceStep(
                "Restart only the affected TruePanel component first",
                "Prefer a narrow TruePanel service recovery before rebooting the NAS or changing hardware.",
            ),
        ),
        verification=(
            GuidanceStep(
                "Verify controller communication",
                "Require successful controller I/O and a healthy reader/dispatcher state before clearing the fault.",
            ),
        ),
        escalation=(
            "Escalate to hardware inspection only after software/service recovery and serial-device checks fail."
        ),
        model_specific=True,
        sources=(QNAP_TVS_X71_MANUAL,),
    ),
    "telemetry.stale": FaultGuidance(
        code="telemetry.stale",
        title="Hardware telemetry is stale",
        severity="caution",
        summary=(
            "TruePanel is no longer receiving sufficiently fresh hardware observations to make normal automated decisions."
        ),
        evidence_fields=(
            "telemetry_age_seconds",
            "last_fresh_timestamp",
            "missing_domains",
            "host_agent_state",
            "control_authority",
            "safety_hold",
        ),
        immediate_actions=(
            GuidanceStep(
                "Treat unknown hardware state conservatively",
                "Suppress decisions that depend on fresh telemetry and keep control in the project's defined fail-safe state.",
            ),
        ),
        diagnosis=(
            GuidanceStep(
                "Locate the stale boundary",
                "Determine whether all Host Agent data is stale or only a specific source such as hwmon, enclosure, or network telemetry.",
            ),
        ),
        remediation=(
            GuidanceStep(
                "Recover the narrowest failed producer",
                "Restore the affected collector or Host Agent path before considering a full service or NAS restart.",
            ),
        ),
        verification=(
            GuidanceStep(
                "Require sustained fresh observations",
                "Do not clear the warning on one sample. Require multiple fresh observations and successful safety-policy reevaluation.",
            ),
        ),
        escalation=(
            "Escalate if telemetry remains stale after collector/service recovery or if stale data coincides with an active thermal or storage fault."
        ),
        model_specific=False,
        sources=(),
    ),
}


HOLODECK_MISSION_GUIDANCE: Final[dict[str, tuple[str, ...]]] = {
    "thermal-ramp": ("thermal.high_temperature",),
    "fan-stall-recovery": ("cooling.fan_stall",),
    "drive-failure": ("storage.disk_faulted", "storage.pool_degraded"),
    "drive-failure-recovery": ("storage.disk_faulted", "storage.pool_degraded"),
    "drive-removal": ("storage.pool_degraded",),
    "drive-removal-reinsert": ("storage.pool_degraded",),
    "network-flap": ("network.link_down",),
    "lcd-loss-recovery": ("front_panel.lcd_unavailable",),
    "stale-telemetry-recovery": ("telemetry.stale",),
}


def guidance_codes() -> tuple[str, ...]:
    """Return guidance codes in stable catalog order."""

    return tuple(_CATALOG)


def guidance_for(code: str) -> FaultGuidance:
    """Return guidance for a normalized fault code."""

    key = str(code).strip().lower()
    try:
        return _CATALOG[key]
    except KeyError as error:
        available = ", ".join(guidance_codes())
        raise ValueError(
            f"unknown operator guidance code: {code!r}; available: {available}"
        ) from error


def guidance_payload(code: str) -> dict[str, object]:
    """Return a JSON-serializable Mission Control guidance payload."""

    return asdict(guidance_for(code))


def guidance_for_mission(name: str) -> tuple[FaultGuidance, ...]:
    """Return guidance entries exercised by a built-in HoloDeck mission."""

    key = str(name).strip().lower()
    try:
        codes = HOLODECK_MISSION_GUIDANCE[key]
    except KeyError as error:
        available = ", ".join(HOLODECK_MISSION_GUIDANCE)
        raise ValueError(
            f"unknown HoloDeck guidance mission: {name!r}; available: {available}"
        ) from error
    return tuple(guidance_for(code) for code in codes)


__all__ = [
    "FaultGuidance",
    "GuidanceSource",
    "GuidanceStep",
    "HOLODECK_MISSION_GUIDANCE",
    "guidance_codes",
    "guidance_for",
    "guidance_for_mission",
    "guidance_payload",
]
