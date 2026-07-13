#!/usr/bin/env python3

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from truepanel.display.animations import startup_frames
from truepanel.display.canvas import Canvas
from truepanel.display.widgets import (
    activity_meter,
    dual_meter,
    labeled_bar,
    progress_bar,
    sparkline,
    spinner,
)


def show(lines, delay=0.35):
    print("\033[2J\033[H", end="")
    print("+----------------+")
    for line in lines:
        print(f"|{line[:16].ljust(16)}|")
    print("+----------------+")
    time.sleep(delay)


def main():
    for lines in startup_frames():
        show(lines, 0.08)

    examples = []

    examples.append([
        labeled_bar("CPU", 64),
        labeled_bar("RAM", 82),
    ])

    examples.append([
        dual_meter("CPU", 42, "RAM", 71),
        f"I/O {activity_meter(73, width=12)}",
    ])

    examples.append([
        "POOL O HEALTHY",
        f"USED {progress_bar(68, width=11)}",
    ])

    examples.append([
        "CPU HISTORY",
        sparkline([12, 18, 44, 39, 72, 91, 65, 50], width=16),
    ])

    for lines in examples:
        canvas = Canvas()
        canvas.text(0, 0, lines[0])
        canvas.text(0, 1, lines[1])
        show(canvas.lines, 1.5)

    for frame in range(12):
        canvas = Canvas()
        canvas.text(0, 0, "TruePanel Active")
        canvas.text(0, 1, f"{spinner(frame)} Graphics Ready")
        show(canvas.lines, 0.15)


if __name__ == "__main__":
    main()
