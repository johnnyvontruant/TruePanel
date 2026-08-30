#!/usr/bin/env python3
"""Exercise an installed TruePanel wheel outside its source checkout."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path


def run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def main() -> int:
    executable = Path(sys.executable).with_name("truepanel")
    if not executable.is_file():
        raise RuntimeError(f"installed truepanel command is missing: {executable}")

    with tempfile.TemporaryDirectory(prefix="truepanel-wheel-smoke-") as directory:
        outside = Path(directory)
        import_check = run(
            [
                sys.executable,
                "-I",
                "-c",
                (
                    "import pathlib, truepanel, truepanel.cli; "
                    "path = pathlib.Path(truepanel.__file__).resolve(); "
                    "assert 'site-packages' in str(path), path; "
                    "print(path)"
                ),
            ],
            cwd=outside,
        )
        assert "site-packages" in import_check.stdout

        corpus_check = run(
            [
                sys.executable,
                "-I",
                "-c",
                (
                    "from truepanel.holodeck.aegis_corpus import "
                    "run_black_box_corpus; "
                    "report = run_black_box_corpus(); "
                    "assert report['corpus_size'] == 6; "
                    "assert report['confusion_matrix']['false_positive'] == 0; "
                    "from truepanel.aegis.evidence_gate import "
                    "builtin_lab_evidence_status; "
                    "gate = builtin_lab_evidence_status(); "
                    "assert gate['stage'] == 'lab_calibrated'; "
                    "assert gate['production_validated'] is False"
                ),
            ],
            cwd=outside,
        )
        assert corpus_check.returncode == 0

        field_smoke = run(
            [
                str(executable),
                "holodeck",
                "field-smoke",
                str(outside / "field-workflow"),
            ],
            cwd=outside,
        )
        field_receipt = json.loads(field_smoke.stdout)
        assert field_receipt["stage"] == "lab_calibrated"
        assert field_receipt["production_validated"] is False
        assert field_receipt["hardware_isolated"] is True
        assert field_receipt["control_authority"] is False

        reported = run([str(executable), "version"], cwd=outside)
        assert f"Version: {version('truepanel')}" in reported.stdout

        simulated = run(
            [
                str(executable),
                "holodeck",
                "run",
                "battlestation",
                "--steps",
                "1",
                "--json",
            ],
            cwd=outside,
        )
        state = json.loads(simulated.stdout)
        assert state["system"]["hostname"] == "HoloDeck-BattleStation"
        assert state["read_only"] is True

        injected = run(
            [
                str(executable),
                "holodeck",
                "inject",
                "fan_stall",
                "channel=1",
            ],
            cwd=outside,
        )
        fault = json.loads(injected.stdout)
        assert fault["fans"]["fan_channels"][0]["rpm"] == 0

        checked = run(
            [
                str(executable),
                "holodeck",
                "check",
                "battlestation",
                "--steps",
                "2",
                "--json",
            ],
            cwd=outside,
        )
        assert json.loads(checked.stdout)["passed"] is True

        recording = outside / "incident.jsonl"
        recording.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "privacy": "sanitized",
                    "captured_at": 10,
                    "sequence": 1,
                    "telemetry": {},
                    "lcd": {},
                    "fan": {
                        "fan_channels": [
                            {
                                "number": 1,
                                "rpm": 0,
                                "stalled": True,
                                "healthy": True,
                                "alarm": False,
                            }
                        ]
                    },
                    "storage": {},
                    "alerts": [],
                    "buttons": {},
                    "mission_control": {},
                },
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        replayed = run(
            [
                str(executable),
                "holodeck",
                "replay",
                str(recording),
                "--json",
            ],
            cwd=outside,
        )
        assert len(replayed.stdout.splitlines()) == 1

        output = outside / "compiled.json"
        compiled = run(
            [
                str(executable),
                "holodeck",
                "compile-incident",
                str(recording),
                "--invariant",
                "cooling.stalled_not_healthy",
                "--output",
                str(output),
            ],
            cwd=outside,
        )
        manifest = json.loads(compiled.stdout)
        artifact = json.loads(output.read_text(encoding="utf-8"))
        assert manifest == artifact["manifest"]
        assert manifest["minimized_frame_count"] == 1
        assert manifest["executable_code_generated"] is False

    print("PASS: installed TruePanel wheel, HoloDeck CLI, and AEGIS corpus smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
