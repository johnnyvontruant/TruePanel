"""
Compatibility survey presentation.
"""

from __future__ import annotations

import json
from pathlib import Path

from .checks import collect_compatibility
from .models import CompatibilityReport
from .support import write_support_bundle


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
    support_bundle: bool = False,
    output: str | Path | None = None,
) -> int:
    report = collect_compatibility()

    if support_bundle:
        path = write_support_bundle(
            report,
            output=output,
        )

        print()
        print("TruePanel Support Bundle")
        print("========================")
        print(f"Written: {path}")
        print(
            "Privacy: hostnames, addresses, serials, "
            "WWIDs, MACs, usernames, and secrets excluded"
        )

    elif json_output:
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
