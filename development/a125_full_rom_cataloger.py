#!/usr/bin/env python3
"""
Interactive cataloger for the complete A125 display character space.

Each byte from 0x00 through 0xFF is displayed individually. The operator can
compare the physical glyph against external character-ROM charts and record a
match, description, usefulness rating, and optional notes.

The catalog is checkpointed after every character so an interrupted session
can be resumed safely.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from truepanel.lab.capture import open_controller


DEFAULT_OUTPUT_DIR = Path("development/rom_atlas")
DEFAULT_START = 0x00
DEFAULT_END = 0xFF
LCD_WIDTH = 16


def parse_byte(value: str) -> int:
    """
    Parse decimal or hexadecimal byte notation.

    Examples:
        128
        0x80
        FF
    """

    text = str(value).strip()

    if text.lower().startswith("0x"):
        number = int(text, 16)
    elif any(character in "abcdefABCDEF" for character in text):
        number = int(text, 16)
    else:
        number = int(text, 10)

    if not 0 <= number <= 0xFF:
        raise argparse.ArgumentTypeError(
            "byte must be between 0x00 and 0xFF"
        )

    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Display and catalog every A125 ROM character byte."
        )
    )

    parser.add_argument(
        "--start",
        type=parse_byte,
        default=DEFAULT_START,
        help="first byte to inspect, default 0x00",
    )
    parser.add_argument(
        "--end",
        type=parse_byte,
        default=DEFAULT_END,
        help="last byte to inspect, default 0xFF",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="catalog output directory",
    )
    parser.add_argument(
        "--session",
        default="a125-full-rom",
        help="catalog session name",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="ignore an existing checkpoint",
    )

    return parser


def session_paths(
    output_dir: Path,
    session: str,
) -> dict[str, Path]:
    safe_session = "".join(
        character
        if character.isalnum() or character in "-_"
        else "-"
        for character in session.strip()
    ).strip("-")

    if not safe_session:
        safe_session = "a125-full-rom"

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    return {
        "checkpoint": output_dir / f"{safe_session}.json",
        "csv": output_dir / f"{safe_session}.csv",
        "report": output_dir / f"{safe_session}.txt",
    }


def load_entries(
    checkpoint: Path,
) -> dict[int, dict]:
    if not checkpoint.exists():
        return {}

    data = json.loads(
        checkpoint.read_text(
            encoding="utf-8"
        )
    )

    entries = {}

    for item in data.get("entries", []):
        entries[int(item["value"])] = item

    return entries


def save_catalog(
    paths: dict[str, Path],
    entries: dict[int, dict],
    *,
    session: str,
    start: int,
    end: int,
) -> None:
    ordered = [
        entries[value]
        for value in sorted(entries)
    ]

    document = {
        "session": session,
        "range": {
            "start": start,
            "start_hex": f"0x{start:02X}",
            "end": end,
            "end_hex": f"0x{end:02X}",
        },
        "updated_at": datetime.now().isoformat(
            timespec="seconds"
        ),
        "entry_count": len(ordered),
        "entries": ordered,
    }

    paths["checkpoint"].write_text(
        json.dumps(
            document,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    with paths["csv"].open(
        "w",
        newline="",
        encoding="utf-8",
    ) as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=(
                "hex",
                "decimal",
                "chart",
                "match",
                "category",
                "useful",
                "confidence",
                "notes",
            ),
        )

        writer.writeheader()

        for item in ordered:
            writer.writerow(
                {
                    "hex": item["hex"],
                    "decimal": item["value"],
                    "chart": item["chart"],
                    "match": item["match"],
                    "category": item["category"],
                    "useful": item["useful"],
                    "confidence": item["confidence"],
                    "notes": item["notes"],
                }
            )

    lines = [
        "Project Stargate A125 ROM Atlas",
        "=" * 34,
        "",
        f"Session: {session}",
        f"Range: 0x{start:02X}-0x{end:02X}",
        f"Entries: {len(ordered)}",
        "",
    ]

    for item in ordered:
        lines.extend(
            (
                f"{item['hex']} ({item['value']:>3})",
                f"  Chart:      {item['chart'] or '-'}",
                f"  Match:      {item['match'] or '-'}",
                f"  Category:   {item['category'] or '-'}",
                f"  Useful:     {item['useful'] or '-'}",
                f"  Confidence: {item['confidence'] or '-'}",
                f"  Notes:      {item['notes'] or '-'}",
                "",
            )
        )

    paths["report"].write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def prompt(
    label: str,
    default: str = "",
) -> str:
    suffix = (
        f" [{default}]"
        if default
        else ""
    )

    value = input(
        f"{label}{suffix}: "
    ).strip()

    return value or default


def prompt_entry(
    value: int,
    existing: dict | None = None,
) -> dict:
    existing = existing or {}

    print()
    print("=" * 52)
    print(
        f"Character 0x{value:02X} "
        f"(decimal {value})"
    )
    print("=" * 52)
    print(
        "Commands at the first prompt: "
        "q=quit, s=skip, b=go back, "
        "d=mark duplicate"
    )

    chart = prompt(
        "Chart or ROM family",
        existing.get("chart", ""),
    )

    command = chart.lower()

    if command in {"q", "quit"}:
        return {"command": "quit"}

    if command in {"s", "skip"}:
        return {"command": "skip"}

    if command in {"b", "back"}:
        return {"command": "back"}

    if command in {"d", "duplicate"}:
        duplicate = prompt(
            "Duplicate of which byte",
            existing.get("match", ""),
        )

        return {
            "command": "save",
            "value": value,
            "hex": f"0x{value:02X}",
            "chart": "duplicate",
            "match": duplicate,
            "category": "duplicate",
            "useful": "no",
            "confidence": prompt(
                "Confidence low/medium/high",
                existing.get(
                    "confidence",
                    "high",
                ),
            ),
            "notes": prompt(
                "Notes",
                existing.get("notes", ""),
            ),
        }

    match = prompt(
        "Matching chart symbol or cell",
        existing.get("match", ""),
    )

    category = prompt(
        (
            "Category "
            "(letter/number/punctuation/icon/"
            "block/line/duplicate/blank/unknown)"
        ),
        existing.get("category", ""),
    )

    useful = prompt(
        "Useful? yes/no/maybe",
        existing.get("useful", ""),
    )

    confidence = prompt(
        "Confidence low/medium/high",
        existing.get("confidence", ""),
    )

    notes = prompt(
        "Notes",
        existing.get("notes", ""),
    )

    return {
        "command": "save",
        "value": value,
        "hex": f"0x{value:02X}",
        "chart": chart,
        "match": match,
        "category": category,
        "useful": useful,
        "confidence": confidence,
        "notes": notes,
    }


def display_character(
    controller,
    value: int,
) -> None:
    controller.write_frame(
        f"BYTE 0x{value:02X} {value:>3}",
        bytes([value]) * LCD_WIDTH,
    )


def main() -> int:
    args = build_parser().parse_args()

    if args.end < args.start:
        raise SystemExit(
            "--end must be greater than or equal to --start"
        )

    paths = session_paths(
        args.output_dir,
        args.session,
    )

    entries = (
        {}
        if args.no_resume
        else load_entries(
            paths["checkpoint"]
        )
    )

    print("Project Stargate A125 ROM Cataloger")
    print("===================================")
    print(
        f"Range: 0x{args.start:02X}-"
        f"0x{args.end:02X}"
    )
    print(
        f"Existing entries: {len(entries)}"
    )
    print(
        "The catalog is saved after every character."
    )
    print()

    current = args.start

    with open_controller(
        "a125-full-rom-catalog",
        "/dev/ttyS1",
        1200,
        1.0,
        "development/logs",
    ) as (controller, capture):
        controller.backlight(True)
        controller.clear()

        while current <= args.end:
            display_character(
                controller,
                current,
            )

            existing = entries.get(
                current
            )

            result = prompt_entry(
                current,
                existing,
            )

            command = result["command"]

            if command == "quit":
                break

            if command == "back":
                current = max(
                    args.start,
                    current - 1,
                )
                continue

            if command == "skip":
                current += 1
                continue

            entries[current] = {
                key: value
                for key, value in result.items()
                if key != "command"
            }

            save_catalog(
                paths,
                entries,
                session=args.session,
                start=args.start,
                end=args.end,
            )

            current += 1

        controller.clear()

    save_catalog(
        paths,
        entries,
        session=args.session,
        start=args.start,
        end=args.end,
    )

    print()
    print("Capture:   ", capture)
    print("Checkpoint:", paths["checkpoint"])
    print("CSV:       ", paths["csv"])
    print("Report:    ", paths["report"])
    print(
        f"Recorded:   {len(entries)} characters"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
