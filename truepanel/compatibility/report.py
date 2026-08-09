"""
Compatibility survey presentation.
"""

from __future__ import annotations

import json

from .checks import collect_compatibility
from .models import CompatibilityReport


def print_report(
    report: CompatibilityReport,
) -> None:
    print()
    print("TruePanel Compatibility Survey")
    print("==============================")
    print()

    for item in report.checks:
        print(
            f"{item.status:<7} "
            f"{item.name:<22} "
            f"{item.detail}"
        )

    print()
    print("Readiness")
    print("---------")
    print(
        f"Compatibility     : "
        f"{report.classification}"
    )
    print(
        f"Installation Mode : "
        f"{report.installation_mode}"
    )
    print(
        f"Hardware Control  : "
        f"{report.hardware_control}"
    )


def run_compatibility(
    *,
    json_output: bool = False,
) -> int:
    report = collect_compatibility()

    if json_output:
        print(
            json.dumps(
                report.to_dict(),
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print_report(report)

    return 1 if report.classification == "UNSUPPORTED" else 0
