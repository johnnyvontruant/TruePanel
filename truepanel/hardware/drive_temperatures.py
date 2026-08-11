"""
Read-only storage temperature collection.

This provider preserves TruePanel's established drive-temperature behavior
while allowing privileged Host Agent safety telemetry to operate independently
from the legacy application collector.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable

CommandRunner = Callable[[str], str]


def _shell(command: str) -> str:
    try:
        return subprocess.check_output(
            command,
            shell=True,
            universal_newlines=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def parse_legacy_smart_temperature(
    output: str,
) -> int | None:
    """
    Parse temperature exactly as the legacy TruePanel collector did.
    """

    temperature = None

    for line in output.splitlines():
        lower = line.lower()

        if (
            "temperature_celsius" in lower
            or "airflow_temperature" in lower
        ):
            for part in reversed(
                line.split()
            ):
                cleaned = part.strip(
                    "()"
                )

                if cleaned.isdigit():
                    temperature = int(
                        cleaned
                    )
                    break

        if (
            temperature is None
            and line.strip().startswith(
                "Temperature:"
            )
        ):
            for part in line.split():
                if part.isdigit():
                    temperature = int(
                        part
                    )
                    break

        if temperature is not None:
            break

    return temperature


class DriveTemperatureProvider:
    """
    Collect temperatures using TruePanel's established SMART parser.

    The sdf exclusion is intentionally retained during Host Agent migration.
    """

    def __init__(
        self,
        *,
        runner: CommandRunner = _shell,
        excluded_devices: tuple[str, ...] = (
            "sdf",
        ),
    ) -> None:
        self._runner = runner
        self._excluded_devices = {
            str(device).strip()
            for device in excluded_devices
            if str(device).strip()
        }

    def devices(
        self,
    ) -> tuple[str, ...]:
        output = self._runner(
            "lsblk -ndo NAME,TYPE | "
            "awk '$2==\"disk\""
            "{print \"/dev/\"$1}'"
        )

        return tuple(
            line.strip()
            for line in output.splitlines()
            if line.strip()
        )

    def records(
        self,
    ) -> list[dict[str, int | str]]:
        records = []

        for device in self.devices():
            name = device.rsplit(
                "/",
                1,
            )[-1]

            if (
                name
                in self._excluded_devices
            ):
                continue

            output = self._runner(
                f"smartctl -a "
                f"{device} "
                "2>/dev/null"
            )

            temperature = (
                parse_legacy_smart_temperature(
                    output
                )
            )

            if temperature is None:
                continue

            records.append(
                {
                    "drive": name,
                    "temp": temperature,
                }
            )

        records.sort(
            key=lambda item: item[
                "temp"
            ],
            reverse=True,
        )

        return records

    def temperatures(
        self,
    ) -> tuple[float, ...]:
        return tuple(
            float(item["temp"])
            for item in self.records()
        )

    def __call__(
        self,
    ) -> tuple[float, ...]:
        return self.temperatures()


__all__ = [
    "DriveTemperatureProvider",
    "parse_legacy_smart_temperature",
]
