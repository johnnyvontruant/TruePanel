"""
Passive TruePanel compatibility checks.

Compatibility inspection is deliberately read-only. This module does not open
serial ports, write sysfs values, change configuration, invoke hardware-control
commands, or alter service state.
"""

from __future__ import annotations

import platform
import shutil
from pathlib import Path
from typing import Callable

from truepanel.hardware.commands import build_storage_report
from truepanel.hardware.discovery import find_fintek_hwmon
from truepanel.hardware.enclosure import EnclosureController
from truepanel.hardware.manager import HardwareManager

from .models import CompatibilityCheck, CompatibilityReport


PASS = "PASS"
REVIEW = "REVIEW"
FAIL = "FAIL"

SUPPORTED = "SUPPORTED"
PARTIAL = "PARTIAL"
UNSUPPORTED = "UNSUPPORTED"
NEEDS_REVIEW = "REVIEW"

OBSERVATION_ONLY = "OBSERVATION ONLY"
CONTROL_LOCKED = "LOCKED - COMMISSIONING REQUIRED"


def check(
    status: str,
    name: str,
    detail: str,
) -> CompatibilityCheck:
    return CompatibilityCheck(
        status=status,
        name=name,
        detail=detail,
    )


def _read_text(path: Path) -> str:
    try:
        return path.read_text(
            encoding="utf-8",
            errors="replace",
        ).strip()
    except (
        FileNotFoundError,
        PermissionError,
        IsADirectoryError,
        OSError,
    ):
        return ""


def _platform_checks(
    root: Path,
) -> tuple[list[CompatibilityCheck], bool, bool]:
    checks: list[CompatibilityCheck] = []

    version = _read_text(root / "etc/version")

    truenas_ready = bool(version)

    if truenas_ready:
        checks.append(
            check(
                PASS,
                "TrueNAS SCALE",
                version,
            )
        )
    else:
        checks.append(
            check(
                FAIL,
                "TrueNAS SCALE",
                "/etc/version not detected",
            )
        )

    machine = platform.machine() or "unknown"
    architecture_ready = machine.lower() in {
        "x86_64",
        "amd64",
    }

    checks.append(
        check(
            PASS if architecture_ready else REVIEW,
            "Architecture",
            machine,
        )
    )

    return checks, truenas_ready, architecture_ready


def _identity_check(
    root: Path,
) -> CompatibilityCheck:
    dmi = root / "sys/class/dmi/id"

    values = {
        "vendor": _read_text(dmi / "sys_vendor"),
        "product": _read_text(dmi / "product_name"),
        "version": _read_text(dmi / "product_version"),
        "board_vendor": _read_text(dmi / "board_vendor"),
        "board": _read_text(dmi / "board_name"),
    }

    combined = " ".join(values.values()).lower()

    detail_parts = [
        value
        for value in (
            values["vendor"],
            values["product"],
        )
        if value
    ]

    detail = " / ".join(detail_parts) or "DMI identity unavailable"

    if "qnap" in combined:
        return check(
            PASS,
            "QNAP Identity",
            detail,
        )

    return check(
        REVIEW,
        "QNAP Identity",
        (
            f"{detail}; OEM DMI may not expose the "
            "chassis manufacturer"
        ),
    )


def _fintek_check(
    finder: Callable[[], object],
) -> tuple[CompatibilityCheck, bool]:
    try:
        device = finder()
    except Exception as error:
        return (
            check(
                REVIEW,
                "Fan Controller",
                f"discovery error: {error}",
            ),
            False,
        )

    if device is None:
        return (
            check(
                REVIEW,
                "Fan Controller",
                "Fintek-compatible hwmon interface not detected",
            ),
            False,
        )

    return (
        check(
            PASS,
            "Fan Controller",
            f"Fintek-compatible hwmon at {device}",
        ),
        True,
    )


def _fan_channel_checks(
    finder: Callable[[], object],
) -> tuple[list[CompatibilityCheck], bool]:
    """
    Inventory passive fan and PWM interfaces.

    This check inspects file presence only. It does not read PWM values,
    change enable modes, or actuate hardware.
    """

    try:
        device = finder()
    except Exception as error:
        return (
            [
                check(
                    REVIEW,
                    "Fan Channels",
                    f"discovery error: {error}",
                )
            ],
            False,
        )

    if device is None:
        return (
            [
                check(
                    REVIEW,
                    "Fan Telemetry",
                    "no compatible hwmon controller detected",
                ),
                check(
                    REVIEW,
                    "PWM Interfaces",
                    "no compatible hwmon controller detected",
                ),
            ],
            False,
        )

    base = Path(device)

    fan_inputs = sorted(
        path.name
        for path in base.glob("fan*_input")
        if path.is_file()
    )

    pwm_interfaces = []

    for pwm in sorted(base.glob("pwm[0-9]*")):
        name = pwm.name

        if name.endswith("_enable"):
            continue

        suffix = name.removeprefix("pwm")

        if not suffix.isdigit():
            continue

        enable = base / f"{name}_enable"

        pwm_interfaces.append(
            {
                "pwm": name,
                "enable": enable.is_file(),
            }
        )

    if fan_inputs:
        telemetry = check(
            PASS,
            "Fan Telemetry",
            ", ".join(fan_inputs),
        )
    else:
        telemetry = check(
            REVIEW,
            "Fan Telemetry",
            "no fan*_input interfaces detected",
        )

    if pwm_interfaces:
        pwm_detail = ", ".join(
            (
                f"{entry['pwm']} + "
                f"{entry['pwm']}_enable"
                if entry["enable"]
                else f"{entry['pwm']} only"
            )
            for entry in pwm_interfaces
        )

        complete_pwm = all(
            entry["enable"]
            for entry in pwm_interfaces
        )

        pwm = check(
            PASS if complete_pwm else REVIEW,
            "PWM Interfaces",
            pwm_detail,
        )
    else:
        complete_pwm = False
        pwm = check(
            REVIEW,
            "PWM Interfaces",
            "no pwm interfaces detected",
        )

    ready = bool(fan_inputs)

    return (
        [
            telemetry,
            pwm,
        ],
        ready,
    )


def _enclosure_check(
    enclosure: EnclosureController,
) -> tuple[CompatibilityCheck, bool]:
    try:
        enclosures = enclosure.enclosures()
        slots = enclosure.slots()
        populated = enclosure.populated_slots()
    except Exception as error:
        return (
            check(
                REVIEW,
                "Enclosure Topology",
                f"discovery error: {error}",
            ),
            False,
        )

    if not enclosures:
        return (
            check(
                REVIEW,
                "Enclosure Topology",
                "no Linux enclosure interface detected",
            ),
            False,
        )

    names = ", ".join(
        path.name
        for path in enclosures
    )

    return (
        check(
            PASS,
            "Enclosure Topology",
            (
                f"{names}; {len(slots)} slots, "
                f"{len(populated)} populated"
            ),
        ),
        True,
    )


def _storage_checks(
    report_builder: Callable[[], dict],
) -> list[CompatibilityCheck]:
    """
    Report passive storage topology.

    Storage layout is descriptive evidence only and does not affect the
    compatibility classification.
    """

    try:
        payload = report_builder()
    except Exception as error:
        return [
            check(
                REVIEW,
                "Storage Discovery",
                f"inventory error: {error}",
            ),
            check(
                REVIEW,
                "Storage Topology",
                "inventory unavailable",
            ),
        ]

    counts = payload.get("category_counts", {})
    total = int(payload.get("device_count", 0))

    front_bays = int(counts.get("front_bay", 0))
    internal_nvme = int(counts.get("internal_nvme", 0))
    boot_media = int(counts.get("boot_media", 0))
    unassigned = int(counts.get("unassigned", 0))

    def device_count_detail(count: int) -> str:
        noun = "device" if count == 1 else "devices"
        return f"{count} {noun} classified"

    results = [
        check(
            PASS if total else REVIEW,
            "Storage Discovery",
            f"{total} whole-disk devices discovered",
        ),
        check(
            PASS if front_bays else REVIEW,
            "Front-Bay Storage",
            device_count_detail(front_bays),
        ),
        check(
            PASS if internal_nvme else REVIEW,
            "Internal NVMe",
            device_count_detail(internal_nvme),
        ),
        check(
            PASS if boot_media else REVIEW,
            "Boot Media",
            device_count_detail(boot_media),
        ),
    ]

    if unassigned:
        results.append(
            check(
                REVIEW,
                "Unassigned Storage",
                f"{unassigned} devices require topology review",
            )
        )
    else:
        results.append(
            check(
                PASS,
                "Storage Topology",
                "all discovered devices classified",
            )
        )

    return results


def _zfs_visibility_check() -> CompatibilityCheck:
    """
    Check whether ZFS tooling is available without invoking it.
    """

    zpool = shutil.which("zpool")

    if zpool:
        return check(
            PASS,
            "ZFS Visibility",
            f"zpool available at {zpool}; not invoked",
        )

    return check(
        REVIEW,
        "ZFS Visibility",
        "zpool command not found",
    )


def _default_storage_report() -> dict:
    """
    Build the existing read-only TruePanel storage inventory.
    """

    return build_storage_report(
        HardwareManager()
    )


def _front_panel_check(
    root: Path,
) -> tuple[CompatibilityCheck, bool]:
    serial_device = root / "dev/ttyS1"

    if not serial_device.exists():
        return (
            check(
                REVIEW,
                "Front Panel Serial",
                "/dev/ttyS1 not detected",
            ),
            False,
        )

    return (
        check(
            PASS,
            "Front Panel Serial",
            (
                "/dev/ttyS1 present; controller was not "
                "opened or actively probed"
            ),
        ),
        True,
    )


def _classify(
    *,
    truenas_ready: bool,
    architecture_ready: bool,
    fintek_ready: bool,
    enclosure_ready: bool,
    front_panel_ready: bool,
) -> str:
    if not truenas_ready:
        return UNSUPPORTED

    if not architecture_ready:
        return NEEDS_REVIEW

    passive_capabilities = sum(
        (
            fintek_ready,
            enclosure_ready,
            front_panel_ready,
        )
    )

    if passive_capabilities == 3:
        return SUPPORTED

    if passive_capabilities:
        return PARTIAL

    return NEEDS_REVIEW


def collect_compatibility(
    *,
    root: str | Path = "/",
    fintek_finder: Callable[[], object] = find_fintek_hwmon,
    enclosure: EnclosureController | None = None,
    storage_reporter: Callable[[], dict] = _default_storage_report,
) -> CompatibilityReport:
    """
    Inspect passive TruePanel compatibility signals.

    No compatibility result grants permission to actuate hardware.
    """

    root_path = Path(root)

    checks, truenas_ready, architecture_ready = (
        _platform_checks(root_path)
    )

    checks.append(
        _identity_check(root_path)
    )

    fintek_result, fintek_ready = _fintek_check(
        fintek_finder
    )
    checks.append(fintek_result)

    fan_checks, fan_telemetry_ready = (
        _fan_channel_checks(
            fintek_finder
        )
    )
    checks.extend(fan_checks)

    enclosure_controller = (
        enclosure
        if enclosure is not None
        else EnclosureController()
    )

    enclosure_result, enclosure_ready = (
        _enclosure_check(
            enclosure_controller
        )
    )
    checks.append(enclosure_result)

    checks.extend(
        _storage_checks(
            storage_reporter
        )
    )

    checks.append(
        _zfs_visibility_check()
    )

    checks.append(
        check(
            PASS,
            "Storage Safety",
            (
                "storage layout reported only; "
                "no pool operations performed"
            ),
        )
    )

    front_panel_result, front_panel_ready = (
        _front_panel_check(root_path)
    )
    checks.append(front_panel_result)

    classification = _classify(
        truenas_ready=truenas_ready,
        architecture_ready=architecture_ready,
        fintek_ready=(
            fintek_ready
            and fan_telemetry_ready
        ),
        enclosure_ready=enclosure_ready,
        front_panel_ready=front_panel_ready,
    )

    checks.append(
        check(
            PASS,
            "Safety Authority",
            (
                "survey is passive; hardware control remains "
                "locked until commissioning"
            ),
        )
    )

    return CompatibilityReport(
        classification=classification,
        installation_mode=OBSERVATION_ONLY,
        hardware_control=CONTROL_LOCKED,
        checks=tuple(checks),
    )
