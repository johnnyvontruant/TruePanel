"""Read-only Flight Recorder inspection: python -m truepanel.flight_logs."""
import argparse
from collections import deque
from pathlib import Path

from truepanel.flight_recorder import DEFAULT_PATH


def recent(path=DEFAULT_PATH, *, limit=50, severity=None, category=None):
    """Read recent matching entries without loading the whole file into memory."""
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    target = Path(path)
    if not target.is_file():
        return []
    severity = severity.upper() if severity else None
    category = category.upper() if category else None
    result = deque(maxlen=limit)
    with target.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            fields = line.rstrip("\n").split(" | ", 3)
            if len(fields) != 4:
                continue
            if severity and fields[1].strip() != severity:
                continue
            if category and fields[2].strip() != category:
                continue
            result.append(line.rstrip("\n"))
    return list(result)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read recent TruePanel Flight Logs")
    parser.add_argument("--lines", type=int, default=50)
    parser.add_argument("--severity", help="e.g. CRITICAL, WARNING, ALERT, INFO")
    parser.add_argument("--category", help="e.g. BUZZER, ALERT, LOADMASTER")
    parser.add_argument("--path", default=DEFAULT_PATH)
    args = parser.parse_args(argv)
    try:
        lines = recent(args.path, limit=args.lines,
                       severity=args.severity, category=args.category)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    for line in lines:
        print(line)


if __name__ == "__main__":
    main()
