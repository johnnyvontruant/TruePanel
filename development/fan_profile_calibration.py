#!/usr/bin/env python3
"""
TruePanel Fan Profile Calibration Lab

Exercises the guarded Mission Control fan-profile API, records stabilized
telemetry, and always restores motherboard automatic control.

No direct sysfs or hardware writes are performed.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "http://127.0.0.1:8787"

PROFILE_SEQUENCE = (
    {
        "name": "automatic",
        "expected_pwm": None,
        "confirmation": None,
    },
    {
        "name": "quiet",
        "expected_pwm": 170,
        "confirmation": None,
    },
    {
        "name": "balanced",
        "expected_pwm": 194,
        "confirmation": None,
    },
    {
        "name": "cooling_boost",
        "expected_pwm": 225,
        "confirmation": None,
    },
    {
        "name": "afterburners",
        "expected_pwm": 255,
        "confirmation": "ENGAGE_AFTERBURNERS",
    },
)


class CalibrationError(RuntimeError):
    """Raised when a guarded calibration operation fails."""


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    body = None
    headers = {
        "Accept": "application/json",
    }

    if payload is not None:
        body = json.dumps(
            payload
        ).encode(
            "utf-8"
        )
        headers[
            "Content-Type"
        ] = "application/json"

    request = Request(
        url,
        data=body,
        headers=headers,
        method=method,
    )

    try:
        with urlopen(
            request,
            timeout=timeout,
        ) as response:
            raw = response.read()
    except HTTPError as error:
        detail = error.read().decode(
            "utf-8",
            errors="replace",
        )

        raise CalibrationError(
            f"HTTP {error.code} from {url}: "
            f"{detail}"
        ) from error
    except URLError as error:
        raise CalibrationError(
            f"Could not reach {url}: {error}"
        ) from error

    try:
        decoded = json.loads(
            raw.decode(
                "utf-8"
            )
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as error:
        raise CalibrationError(
            f"Invalid JSON from {url}"
        ) from error

    if not isinstance(
        decoded,
        dict,
    ):
        raise CalibrationError(
            f"Unexpected response from {url}"
        )

    return decoded


def request_profile(
    base_url: str,
    profile: str,
    *,
    confirmation: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "profile": profile,
    }

    if confirmation is not None:
        payload[
            "confirmation"
        ] = confirmation

    response = request_json(
        base_url
        + "/api/v1/fans/profile",
        method="POST",
        payload=payload,
    )

    if response.get(
        "ok"
    ) is not True:
        raise CalibrationError(
            response.get(
                "message"
            )
            or response.get(
                "error"
            )
            or f"Profile {profile} was rejected."
        )

    return response


def status_payload(
    base_url: str,
) -> dict[str, Any]:
    return request_json(
        base_url
        + "/api/v1/status"
    )


def temperature_values(
    payload: dict[str, Any],
) -> list[float]:
    values: list[float] = []

    storage = payload.get(
        "storage",
        {},
    )

    for item in storage.get(
        "temperatures",
        [],
    ) or []:
        if not isinstance(
            item,
            dict,
        ):
            continue

        value = item.get(
            "temperature_c",
            item.get(
                "temperature",
                item.get(
                    "temp"
                ),
            ),
        )

        try:
            values.append(
                float(value)
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

    return values


def controlled_channels(
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    fans = payload.get(
        "fans",
        {},
    )

    channels = []

    for channel in fans.get(
        "channels",
        [],
    ) or []:
        if not isinstance(
            channel,
            dict,
        ):
            continue

        try:
            number = int(
                channel.get(
                    "number"
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

        if number not in (
            1,
            2,
        ):
            continue

        channels.append(
            channel
        )

    return channels


def capture_sample(
    payload: dict[str, Any],
    *,
    profile: str,
    sample_number: int,
) -> dict[str, Any]:
    fans = payload.get(
        "fans",
        {},
    )
    control = fans.get(
        "control",
        {},
    )

    result: dict[str, Any] = {
        "timestamp": time.time(),
        "profile": profile,
        "sample_number": sample_number,
        "active_profile": control.get(
            "active_profile"
        ),
        "authority": control.get(
            "control_authority"
        ),
        "remaining_seconds": control.get(
            "remaining_seconds"
        ),
        "safety_hold": bool(
            control.get(
                "safety_hold"
            )
        ),
    }

    temperatures = temperature_values(
        payload
    )

    result[
        "peak_temperature_c"
    ] = (
        max(
            temperatures
        )
        if temperatures
        else None
    )

    for channel in controlled_channels(
        payload
    ):
        number = int(
            channel[
                "number"
            ]
        )

        result[
            f"fan{number}_rpm"
        ] = channel.get(
            "rpm"
        )
        result[
            f"fan{number}_pwm"
        ] = channel.get(
            "pwm"
        )
        result[
            f"fan{number}_mode"
        ] = channel.get(
            "pwm_mode"
        )

    return result


def numeric_values(
    samples: list[dict[str, Any]],
    key: str,
) -> list[float]:
    values = []

    for sample in samples:
        value = sample.get(
            key
        )

        try:
            values.append(
                float(value)
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

    return values


def summarize_profile(
    profile: str,
    expected_pwm: int | None,
    samples: list[dict[str, Any]],
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "profile": profile,
        "expected_pwm": expected_pwm,
        "sample_count": len(
            samples
        ),
    }

    for channel in (
        1,
        2,
    ):
        rpm_values = numeric_values(
            samples,
            f"fan{channel}_rpm",
        )
        pwm_values = numeric_values(
            samples,
            f"fan{channel}_pwm",
        )

        summary[
            f"fan{channel}_rpm_min"
        ] = (
            min(rpm_values)
            if rpm_values
            else None
        )
        summary[
            f"fan{channel}_rpm_max"
        ] = (
            max(rpm_values)
            if rpm_values
            else None
        )
        summary[
            f"fan{channel}_rpm_average"
        ] = (
            round(
                statistics.mean(
                    rpm_values
                ),
                1,
            )
            if rpm_values
            else None
        )
        summary[
            f"fan{channel}_pwm_average"
        ] = (
            round(
                statistics.mean(
                    pwm_values
                ),
                1,
            )
            if pwm_values
            else None
        )

    peak_temperatures = numeric_values(
        samples,
        "peak_temperature_c",
    )

    summary[
        "peak_temperature_c"
    ] = (
        max(
            peak_temperatures
        )
        if peak_temperatures
        else None
    )

    return summary


def print_summary(
    summary: dict[str, Any],
) -> None:
    profile = str(
        summary[
            "profile"
        ]
    )

    print(
        f"{profile:16} "
        f"PWM {str(summary.get('expected_pwm')):>4} | "
        f"F1 {str(summary.get('fan1_rpm_average')):>7} RPM | "
        f"F2 {str(summary.get('fan2_rpm_average')):>7} RPM | "
        f"Peak {str(summary.get('peak_temperature_c')):>5} C"
    )


def write_reports(
    output_directory: Path,
    report: dict[str, Any],
) -> tuple[Path, Path]:
    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    json_path = (
        output_directory
        / f"fan_calibration_{stamp}.json"
    )
    csv_path = (
        output_directory
        / f"fan_calibration_{stamp}.csv"
    )

    json_path.write_text(
        json.dumps(
            report,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    samples = report.get(
        "samples",
        [],
    )

    fieldnames = [
        "timestamp",
        "profile",
        "sample_number",
        "active_profile",
        "authority",
        "remaining_seconds",
        "safety_hold",
        "peak_temperature_c",
        "fan1_rpm",
        "fan1_pwm",
        "fan1_mode",
        "fan2_rpm",
        "fan2_pwm",
        "fan2_mode",
    ]

    with csv_path.open(
        "w",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(
            samples
        )

    return (
        json_path,
        csv_path,
    )


def run_calibration(
    *,
    base_url: str,
    stabilization_seconds: float,
    sample_count: int,
    sample_interval: float,
    output_directory: Path,
) -> dict[str, Any]:
    baseline = status_payload(
        base_url
    )

    baseline_control = (
        baseline.get(
            "fans",
            {},
        ).get(
            "control",
            {},
        )
    )

    if baseline_control.get(
        "connected"
    ) is not True:
        raise CalibrationError(
            "Fan-control runtime is not connected."
        )

    if baseline_control.get(
        "safety_hold"
    ):
        raise CalibrationError(
            "Calibration will not run during a safety hold."
        )

    report: dict[str, Any] = {
        "schema_version": 1,
        "started_at": time.time(),
        "base_url": base_url,
        "stabilization_seconds": (
            stabilization_seconds
        ),
        "sample_count_per_profile": (
            sample_count
        ),
        "sample_interval_seconds": (
            sample_interval
        ),
        "samples": [],
        "summaries": [],
    }

    try:
        for profile_spec in PROFILE_SEQUENCE:
            profile = str(
                profile_spec[
                    "name"
                ]
            )
            expected_pwm = profile_spec[
                "expected_pwm"
            ]
            confirmation = profile_spec[
                "confirmation"
            ]

            print(
                f"\n===== {profile.upper()} ====="
            )

            response = request_profile(
                base_url,
                profile,
                confirmation=confirmation,
            )

            print(
                response.get(
                    "message",
                    "Profile applied.",
                )
            )

            print(
                f"Stabilizing for "
                f"{stabilization_seconds:.0f} seconds..."
            )
            time.sleep(
                stabilization_seconds
            )

            profile_samples = []

            for sample_number in range(
                1,
                sample_count + 1,
            ):
                payload = status_payload(
                    base_url
                )
                sample = capture_sample(
                    payload,
                    profile=profile,
                    sample_number=sample_number,
                )

                if sample.get(
                    "active_profile"
                ) != profile:
                    raise CalibrationError(
                        f"Expected profile {profile}, "
                        f"but status reports "
                        f"{sample.get('active_profile')}."
                    )

                if sample.get(
                    "safety_hold"
                ):
                    raise CalibrationError(
                        "Safety hold activated during calibration."
                    )

                profile_samples.append(
                    sample
                )
                report[
                    "samples"
                ].append(
                    sample
                )

                print(
                    "Sample "
                    f"{sample_number}/{sample_count}: "
                    f"F1 {sample.get('fan1_rpm')} RPM, "
                    f"F2 {sample.get('fan2_rpm')} RPM, "
                    f"PWM {sample.get('fan1_pwm')}, "
                    f"Peak {sample.get('peak_temperature_c')} C"
                )

                if sample_number < sample_count:
                    time.sleep(
                        sample_interval
                    )

            summary = summarize_profile(
                profile,
                expected_pwm,
                profile_samples,
            )

            report[
                "summaries"
            ].append(
                summary
            )

            print_summary(
                summary
            )

    finally:
        print(
            "\n===== RESTORE AUTOMATIC ====="
        )

        try:
            response = request_profile(
                base_url,
                "automatic",
            )
            print(
                response.get(
                    "message",
                    "Automatic restored.",
                )
            )
        except Exception as error:
            print(
                "CRITICAL: Automatic restoration "
                f"request failed: {error}",
                file=sys.stderr,
            )

    final_payload = status_payload(
        base_url
    )
    final_control = (
        final_payload.get(
            "fans",
            {},
        ).get(
            "control",
            {},
        )
    )

    report[
        "finished_at"
    ] = time.time()
    report[
        "final_profile"
    ] = final_control.get(
        "active_profile"
    )
    report[
        "final_authority"
    ] = final_control.get(
        "control_authority"
    )
    report[
        "final_safety_hold"
    ] = bool(
        final_control.get(
            "safety_hold"
        )
    )

    json_path, csv_path = write_reports(
        output_directory,
        report,
    )

    print(
        "\n===== CALIBRATION SUMMARY ====="
    )

    for summary in report[
        "summaries"
    ]:
        print_summary(
            summary
        )

    print(
        "\nFinal profile:",
        report[
            "final_profile"
        ],
    )
    print(
        "Final authority:",
        report[
            "final_authority"
        ],
    )
    print(
        "Safety hold:",
        report[
            "final_safety_hold"
        ],
    )
    print(
        "JSON report:",
        json_path,
    )
    print(
        "CSV report:",
        csv_path,
    )

    if (
        report[
            "final_profile"
        ]
        != "automatic"
        or report[
            "final_authority"
        ]
        != "automatic"
        or report[
            "final_safety_hold"
        ]
    ):
        raise CalibrationError(
            "Calibration did not finish in a safe automatic state."
        )

    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a guarded TruePanel fan-profile "
            "calibration sweep."
        )
    )

    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
    )
    parser.add_argument(
        "--stabilize",
        type=float,
        default=8.0,
        help=(
            "Seconds to wait after applying each profile."
        ),
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=4,
        help=(
            "Telemetry samples per profile."
        ),
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help=(
            "Seconds between samples."
        ),
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "development/logs"
        ),
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help=(
            "Print the profile sequence without "
            "changing fan control."
        ),
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.samples < 1:
        parser.error(
            "--samples must be at least 1."
        )

    if args.stabilize < 0:
        parser.error(
            "--stabilize cannot be negative."
        )

    if args.interval < 0:
        parser.error(
            "--interval cannot be negative."
        )

    if args.plan:
        print(
            "TruePanel Fan Calibration Plan"
        )
        print(
            "Direct hardware access: DISABLED"
        )
        print(
            "Command path: guarded Mission Control API"
        )

        for profile in PROFILE_SEQUENCE:
            print(
                f"- {profile['name']}: "
                f"expected PWM "
                f"{profile['expected_pwm']}"
            )

        print(
            "- automatic: always restored at exit"
        )
        return 0

    try:
        run_calibration(
            base_url=args.base_url.rstrip(
                "/"
            ),
            stabilization_seconds=(
                args.stabilize
            ),
            sample_count=args.samples,
            sample_interval=args.interval,
            output_directory=(
                args.output_directory
            ),
        )
    except KeyboardInterrupt:
        print(
            "\nCalibration interrupted.",
            file=sys.stderr,
        )
        return 130
    except CalibrationError as error:
        print(
            f"\nCalibration failed: {error}",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
