"""Passive verification of motherboard fan-control restoration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from truepanel.hardware.discovery import find_fintek_hwmon
from truepanel.hardware.fan_runtime import (
    normalize_fan_control_channels,
)

AUTOMATIC_PWM_ENABLE_MODE = 2


@dataclass(frozen=True)
class FanAutomaticCheck:
    """One read-only motherboard fan-control mode check."""

    channel: int
    path: str
    mode: int | None
    automatic: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "path": self.path,
            "mode": self.mode,
            "automatic": self.automatic,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class HostFanSafetyReport:
    """Passive snapshot of controlled fan-channel restoration safety."""

    fan_control_enabled: bool
    controller_path: str | None
    checks: tuple[FanAutomaticCheck, ...]
    reason: str

    @property
    def applicable(self) -> bool:
        return self.fan_control_enabled

    @property
    def safe(self) -> bool:
        if not self.fan_control_enabled:
            return True

        return bool(self.checks) and all(
            check.automatic
            for check in self.checks
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "fan_control_enabled": self.fan_control_enabled,
            "applicable": self.applicable,
            "safe": self.safe,
            "controller_path": self.controller_path,
            "reason": self.reason,
            "checks": [
                check.to_dict()
                for check in self.checks
            ],
        }


def _fan_settings(
    config: Mapping[str, Any],
) -> Mapping[str, Any]:
    hardware = config.get(
        "hardware",
        {},
    )

    if not isinstance(hardware, Mapping):
        return {}

    settings = hardware.get(
        "fan_control",
        {},
    )

    if not isinstance(settings, Mapping):
        return {}

    return settings


def collect_host_fan_safety(
    config: Mapping[str, Any],
    *,
    controller_path: str | Path | None = None,
    controller_finder: Callable[
        [],
        str | Path | None,
    ] = find_fintek_hwmon,
) -> HostFanSafetyReport:
    """
    Verify configured fan-control channels are back in motherboard Automatic.

    This function is strictly read-only. It does not construct Host runtime,
    request a fan profile, open a command socket, or write sysfs controls.
    """

    settings = _fan_settings(config)
    enabled = bool(
        settings.get(
            "enabled",
            False,
        )
    )

    if not enabled:
        return HostFanSafetyReport(
            fan_control_enabled=False,
            controller_path=None,
            checks=(),
            reason=(
                "Fan control is disabled; TruePanel has no configured "
                "fan-control channels to restore."
            ),
        )

    channels = normalize_fan_control_channels(
        settings.get(
            "controlled_channels",
            (
                1,
                2,
            ),
        )
    )

    if controller_path is None:
        try:
            controller_path = controller_finder()
        except Exception as error:
            return HostFanSafetyReport(
                fan_control_enabled=True,
                controller_path=None,
                checks=(),
                reason=(
                    "Fan controller discovery failed: "
                    f"{type(error).__name__}: {error}"
                ),
            )

    if controller_path is None:
        return HostFanSafetyReport(
            fan_control_enabled=True,
            controller_path=None,
            checks=(),
            reason=(
                "Fan control is enabled but the Fintek controller "
                "is unavailable."
            ),
        )

    base = Path(controller_path)
    checks = []

    for channel in channels:
        mode_path = base / f"pwm{channel}_enable"

        try:
            mode = int(
                mode_path.read_text(
                    encoding="utf-8"
                ).strip()
            )
        except Exception as error:
            checks.append(
                FanAutomaticCheck(
                    channel=channel,
                    path=str(mode_path),
                    mode=None,
                    automatic=False,
                    detail=(
                        "Unable to read motherboard fan-control mode: "
                        f"{type(error).__name__}: {error}"
                    ),
                )
            )
            continue

        automatic = (
            mode == AUTOMATIC_PWM_ENABLE_MODE
        )
        checks.append(
            FanAutomaticCheck(
                channel=channel,
                path=str(mode_path),
                mode=mode,
                automatic=automatic,
                detail=(
                    "Motherboard Automatic mode confirmed."
                    if automatic
                    else (
                        "Expected motherboard Automatic mode 2; "
                        f"observed mode {mode}."
                    )
                ),
            )
        )

    safe = all(
        check.automatic
        for check in checks
    )

    return HostFanSafetyReport(
        fan_control_enabled=True,
        controller_path=str(base),
        checks=tuple(checks),
        reason=(
            "All configured fan-control channels are in motherboard "
            "Automatic mode."
            if safe
            else (
                "One or more configured fan-control channels are not "
                "confirmed in motherboard Automatic mode."
            )
        ),
    )


def format_host_fan_safety(
    report: HostFanSafetyReport,
) -> str:
    """Format a passive fan-restoration verification report."""

    lines = [
        "TruePanel Host Fan Safety",
        "=========================",
        "",
    ]

    if not report.applicable:
        lines.extend(
            [
                "[PASS] Fan control: NOT APPLICABLE",
                report.reason,
            ]
        )
    else:
        for check in report.checks:
            state = "PASS" if check.automatic else "REVIEW"
            mode = (
                str(check.mode)
                if check.mode is not None
                else "unreadable"
            )
            lines.append(
                f"[{state}] channel {check.channel}: "
                f"pwm{check.channel}_enable={mode} "
                f"{check.detail}"
            )

        if not report.checks:
            lines.append(
                f"[REVIEW] {report.reason}"
            )

    lines.extend(
        [
            "",
            (
                "Motherboard fan control: AUTOMATIC"
                if report.safe
                else "Motherboard fan control: REVIEW"
            ),
        ]
    )

    return "\n".join(lines)


__all__ = [
    "AUTOMATIC_PWM_ENABLE_MODE",
    "FanAutomaticCheck",
    "HostFanSafetyReport",
    "collect_host_fan_safety",
    "format_host_fan_safety",
]
