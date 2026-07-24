#!/usr/bin/env python3
"""
Live observe-only thermal fan simulation.

Reads Mission Control telemetry and prints the guarded fan profile TruePanel
would recommend. No profile commands or hardware writes are issued.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.request import urlopen

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(REPOSITORY_ROOT),
    )

from truepanel.hardware.thermal_fan_policy import (
    ThermalFanPolicy,
)


def status_payload(base_url):
    with urlopen(
        base_url + "/api/v1/status",
        timeout=10,
    ) as response:
        return json.load(response)


def temperature_values(payload):
    values = []

    storage = payload.get(
        "storage",
        {},
    )

    for item in storage.get(
        "temperatures",
        [],
    ) or []:
        if not isinstance(item, dict):
            continue

        value = item.get(
            "temperature_c",
            item.get(
                "temperature",
                item.get("temp"),
            ),
        )

        try:
            values.append(float(value))
        except (
            TypeError,
            ValueError,
        ):
            continue

    return values


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Observe live TruePanel temperatures and print "
            "thermal fan recommendations without applying them."
        )
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8787",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=12,
    )
    parser.add_argument(
        "--dwell",
        type=float,
        default=30.0,
    )
    args = parser.parse_args()

    policy = ThermalFanPolicy(
        minimum_dwell_seconds=args.dwell,
    )

    print(
        "TruePanel thermal fan simulation"
    )
    print(
        "OBSERVE ONLY: no fan commands will be sent."
    )

    for sample in range(
        1,
        max(1, args.samples) + 1,
    ):
        payload = status_payload(
            args.base_url
        )
        temperatures = temperature_values(
            payload
        )
        result = policy.evaluate(
            temperatures,
            telemetry_fresh=True,
        )

        hottest = (
            f"{result.hottest_temperature_c:.1f}°C"
            if result.hottest_temperature_c is not None
            else "Unavailable"
        )

        print(
            f"{sample:02d} | "
            f"Hottest {hottest} | "
            f"Recommend "
            f"{result.recommended_profile.value} | "
            f"{result.reason}"
        )

        if sample < args.samples:
            time.sleep(
                max(0.1, args.interval)
            )


if __name__ == "__main__":
    main()
