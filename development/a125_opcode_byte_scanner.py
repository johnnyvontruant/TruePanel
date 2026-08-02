#!/usr/bin/env python3
"""
Project Stargate: A125 opcode byte-pattern scanner.

Every known A125 host command begins with the preamble byte 0x4D
(see docs/A125_PROTOCOL.md). This tool does not touch the serial
controller. It reads arbitrary files -- extracted firmware, shared
libraries, daemons found by qnap_lcd_hal_hunt.sh -- and tallies which
byte follows every 0x4D it finds.

The idea: if the original vendor binary (hal_daemon / libuLinux_hal.so
/ a lcd_tool-style utility) builds A125 packets the same way TruePanel
does, the second byte of each 0x4D pair it contains is a real opcode
the vendor uses. Cross-referencing that tally against the opcodes this
project has already verified, ruled out, or never tried turns a vague
"search the firmware" idea into a concrete, prioritized list of new
opcodes worth taking to a guarded Stargate probe.

This is a first-pass heuristic, not proof:
  - 0x4D is a common byte and will appear in plenty of unrelated
    binary data (offsets, unrelated strings, compiled constants).
  - A real match is much more convincing near an already-identified
    LCD/A125/HAL string or symbol (see qnap_lcd_hal_hunt.sh), or when
    the same (0x4D, opcode) pair repeats across independent files.
  - Nothing found here should go to live hardware without going
    through the normal truepanel.lab.protocol guarded experiment path.

Usage:
    python3 a125_opcode_byte_scanner.py FILE [FILE ...]
    python3 a125_opcode_byte_scanner.py --dir SOME_SYSROOT_SUBDIR
    python3 a125_opcode_byte_scanner.py --dir SYSROOT --min-count 3 --json out.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

PREAMBLE = 0x4D

# Pulled directly from docs/A125_PROTOCOL.md. Keep in sync by hand --
# this script intentionally has no dependency on the truepanel package
# so it can run standalone against a firmware analysis tree.
VERIFIED_OPCODES = {
    0x00: "Get board ID",
    0x02: "Set LED value (vendor static evidence)",
    0x03: "Unknown fixed vendor command",
    0x06: "Get buttons",
    0x07: "Get protocol version",
    0x09: "Set RTC time (vendor static evidence)",
    0x0B: "Unknown fixed vendor command",
    0x0C: "Display write",
    0x0D: "Clear display",
    0x28: "Stop RTC display (vendor static evidence)",
    0x29: "Start RTC display (vendor static evidence)",
    0x35: "Manual adjustment toggle (vendor static evidence)",
    0x5E: "Backlight",
    0xFF: "Reset",
}

# From docs/STARGATE_DISCOVERIES.md: header-only probe, deterministic
# NACK, confirmed NOT valid opcodes.
# Deterministic NACKs from header-only probes. Opcodes requiring
# structured payloads, including 0x09 and possibly 0x0B, do not belong
# in this set merely because a header-only request was rejected.
RULED_OUT_OPCODES = {
    0x08,
    0x0A,
    0x0E,
    0x0F,
    0x10,
}

# Reserved for third-party reports that have not been corroborated by
# live TruePanel work or recovered vendor firmware.
REPORTED_UNVERIFIED_OPCODES = {}

FORBIDDEN_OPCODES = {0xFF}  # never suggest sending this live via this tool


@dataclass
class ScanResult:
    path: str
    total_preambles: int
    opcode_counts: Counter = field(default_factory=Counter)


def classify(opcode: int) -> str:
    if opcode in VERIFIED_OPCODES:
        return "verified"
    if opcode in RULED_OUT_OPCODES:
        return "ruled_out"
    if opcode in REPORTED_UNVERIFIED_OPCODES:
        return "reported_unverified"
    return "unknown"


def scan_file(path: Path) -> ScanResult:
    data = path.read_bytes()
    counts: Counter = Counter()
    total = 0

    # Every 0x4D byte is a candidate preamble; tally whatever follows it.
    # This intentionally overlaps (a run of 0x4D 0x4D 0x4D is scanned at
    # every position) so nothing is missed because of alignment.
    idx = data.find(bytes((PREAMBLE,)))
    while idx != -1 and idx + 1 < len(data):
        opcode = data[idx + 1]
        counts[opcode] += 1
        total += 1
        idx = data.find(bytes((PREAMBLE,)), idx + 1)

    return ScanResult(path=str(path), total_preambles=total, opcode_counts=counts)


def iter_target_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []

    for p in paths:
        if p.is_dir():
            files.extend(sorted(f for f in p.rglob("*") if f.is_file()))
        elif p.is_file():
            files.append(p)

    return files


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Files to scan directly.",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=None,
        help="Recursively scan every file under this directory.",
    )
    parser.add_argument(
        "--min-count",
        type=int,
        default=2,
        help="Only report opcodes seen at least this many times in a "
        "single file (default: 2). Use 1 to see everything.",
    )
    parser.add_argument(
        "--max-file-size",
        type=int,
        default=200 * 1024 * 1024,
        help="Skip files larger than this many bytes (default 200MB).",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        help="Also write the full aggregated tally to this JSON path.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    targets = list(args.paths)
    if args.dir is not None:
        targets.append(args.dir)

    if not targets:
        print("No files or --dir given. Nothing to scan.")
        return 1

    files = [
        f
        for f in iter_target_files(targets)
        if f.stat().st_size <= args.max_file_size
    ]

    if not files:
        print("No readable files found under the given paths.")
        return 1

    print("Project Stargate A125 Opcode Byte Scanner")
    print("=" * 42)
    print(f"Scanning {len(files)} file(s)...")
    print()

    aggregate_counts: Counter = Counter()
    per_file_hits: dict[int, list[str]] = defaultdict(list)
    per_file_reports = []

    for path in files:
        try:
            result = scan_file(path)
        except (OSError, MemoryError) as error:
            print(f"SKIP {path}: {error}")
            continue

        if result.total_preambles == 0:
            continue

        interesting = {
            op: n for op, n in result.opcode_counts.items() if n >= args.min_count
        }

        if not interesting:
            continue

        per_file_reports.append(result)
        aggregate_counts.update(result.opcode_counts)

        for op in interesting:
            per_file_hits[op].append(str(path))

        print(f"FILE: {path}")
        print(f"  total 0x{PREAMBLE:02X} bytes seen: {result.total_preambles}")

        for op, count in sorted(interesting.items(), key=lambda kv: -kv[1]):
            label = classify(op)
            note = ""
            if label == "verified":
                note = f" -- verified: {VERIFIED_OPCODES[op]}"
            elif label == "ruled_out":
                note = " -- already ruled out (deterministic NACK)"
            elif label == "reported_unverified":
                note = f" -- {REPORTED_UNVERIFIED_OPCODES[op]}"
            elif op in FORBIDDEN_OPCODES:
                note = " -- forbidden opcode, never probe automatically"

            print(f"  0x{op:02X}  x{count:<4d} [{label}]{note}")

        print()

    print("=" * 42)
    print("AGGREGATE ACROSS ALL FILES")
    print("=" * 42)

    if not aggregate_counts:
        print("No 0x4D-prefixed opcode candidates met --min-count.")
        return 0

    unknown_candidates = sorted(
        (
            (op, n)
            for op, n in aggregate_counts.items()
            if classify(op) == "unknown" and n >= args.min_count
        ),
        key=lambda kv: -kv[1],
    )

    print()
    print("Unknown opcodes seen after 0x4D, ranked by frequency:")
    print("(cross-check the files listed below against")
    print(" qnap_lcd_hal_hunt.sh output before trusting a hit --")
    print(" a candidate found only in an unrelated binary is weak")
    print(" evidence; the same candidate found in hal_daemon /")
    print(" libuLinux_hal.so / a lcd-named binary is much stronger.)")
    print()

    for op, count in unknown_candidates:
        files_hit = per_file_hits[op]
        print(f"  0x{op:02X}  total x{count}  seen in {len(files_hit)} file(s)")
        for f in files_hit[:5]:
            print(f"      {f}")
        if len(files_hit) > 5:
            print(f"      ... and {len(files_hit) - 5} more")

    if args.json is not None:
        payload = {
            "preamble": f"0x{PREAMBLE:02X}",
            "min_count": args.min_count,
            "files": [
                {
                    "path": r.path,
                    "total_preambles": r.total_preambles,
                    "opcodes": {
                        f"0x{op:02X}": {
                            "count": n,
                            "classification": classify(op),
                        }
                        for op, n in r.opcode_counts.items()
                        if n >= args.min_count
                    },
                }
                for r in per_file_reports
            ],
            "aggregate_unknown_candidates": [
                {
                    "opcode": f"0x{op:02X}",
                    "total_count": n,
                    "files": per_file_hits[op],
                }
                for op, n in unknown_candidates
            ],
        }
        args.json.write_text(json.dumps(payload, indent=2))
        print()
        print(f"Wrote JSON report: {args.json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
