#!/usr/bin/env python3
"""Offline replay of synthetic WINGMAN model responses into a trusted HOLD view.

Only synthetic HoloDeck fixture metadata supplies hold authority. Never infer
a HOLD from model output or user-supplied response files. Does not start models,
read live NAS state, open a network port, or modify production services.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from truepanel.holodeck.wingman import wingman_eval_cases
from truepanel.wingman.hold_envelope import project_operator_view
from truepanel.wingman.service import WingmanServiceResult


def replay(path: Path) -> dict:
    fixture_by_id = {case["case_id"]: case for case in wingman_eval_cases()}
    original = json.loads(path.read_text())
    records = []
    for row in original["cases"]:
        case_id = row["case_id"]
        if case_id not in fixture_by_id:
            raise ValueError(f"Unknown synthetic fixture: {case_id}")
        fixture = fixture_by_id[case_id]
        result = WingmanServiceResult(
            status=row["service_status"],
            advisory=row.get("advisory"),
            source_ids=(),
            errors=tuple(row.get("service_errors") or ()),
        )
        view = project_operator_view(
            result,
            trusted_holds=fixture.get("trusted_holds", ()),
        )
        records.append({
            "case_id": case_id,
            "repeat": row["repeat"],
            "raw_service_status": row["service_status"],
            "raw_errors": row.get("errors", []),
            "operator_view": view,
        })
    return {
        "project": "WINGMAN",
        "source": "SYNTHETIC_HOLODECK_REPLAY_ONLY",
        "original_response_file": str(path),
        "records": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run", required=True, type=Path,
        help="Existing Mac gauntlet run directory, not a model file",
    )
    args = parser.parse_args()
    run = args.run.expanduser().resolve()
    if not run.is_dir():
        parser.error("Run directory does not exist")

    input_files = sorted(run.glob("*/responses.json"))
    if not input_files:
        parser.error("No completed synthetic response files in this run")
    output = run / "hold-envelope-replay.json"
    reports = [replay(path) for path in input_files]
    output.write_text(json.dumps({
        "schema_version": 1,
        "project": "WINGMAN",
        "run": str(run),
        "reports": reports,
    }, indent=2) + "\n")

    print(f"Replay report: {output}")
    for report in reports:
        model = Path(report["original_response_file"]).parent.name
        records = report["records"]
        guarded = [r for r in records
                   if r["operator_view"]["authoritative_holds"]]
        print(
            f"{model}: {len(records)} raw responses; "
            f"{len(guarded)} trusted synthetic HOLD views"
        )
        for row in guarded:
            view = row["operator_view"]
            holds = ", ".join(hold["headline"]
                              for hold in view["authoritative_holds"])
            if view["generated_explanation"] is not None:
                raise RuntimeError("HOLD leaked generated explanation")
            print(
                f"  run {row['repeat']} {row['case_id']}: "
                f"{holds}; model text suppressed"
            )
    print("No model execution or live TrueNAS access was performed.")


if __name__ == "__main__":
    main()
