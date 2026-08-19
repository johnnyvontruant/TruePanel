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

    print("PASS: installed TruePanel wheel and HoloDeck CLI smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
