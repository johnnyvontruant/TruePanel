"""Safe command-line access to Project HANGAR."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .registry import (
    load_registry,
    render_status_views,
    status_summary,
    validate_registry,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m truepanel.hangar")
    actions = parser.add_subparsers(dest="action", required=True)
    validate = actions.add_parser("validate")
    validate.add_argument("--root", type=Path, default=Path.cwd())
    render = actions.add_parser("render")
    render.add_argument("--output", type=Path, default=Path("docs/hangar"))
    actions.add_parser("status")
    args = parser.parse_args(argv)
    registry = load_registry()
    if args.action == "validate":
        errors = validate_registry(registry, root=args.root)
        print(json.dumps({"valid": not errors, "errors": list(errors)}, sort_keys=True))
        return 1 if errors else 0
    if args.action == "render":
        render_status_views(args.output, registry)
        return 0
    print(json.dumps(status_summary(registry), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
