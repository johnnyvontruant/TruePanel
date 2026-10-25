"""Command line for Loadmaster.

python3 -m truepanel.loadmaster run                 run the service on its own
python3 -m truepanel.loadmaster status              print the live status
python3 -m truepanel.loadmaster preview NAME PATH   dry run against a folder
                                                    (e.g. a manually mounted
                                                    spare drive); changes nothing
"""

from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
import threading
from pathlib import Path

from truepanel.config.loader import load_config

from . import build_service, load_settings
from .identity import folder_keys, library_index
from .link import read_status
from .plan import build_plan
from .scan import scan
from .state import StateStore


def _fstype(path: Path) -> str | None:
    """Filesystem type of the mount holding ``path`` (e.g. exfat), if known."""

    try:
        result = subprocess.run(
            ["findmnt", "-no", "FSTYPE", "-T", str(path)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip().lower() or None


def _size(value: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1000 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1000
    return str(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m truepanel.loadmaster")
    parser.add_argument("--config", default="truepanel.yaml")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run")
    sub.add_parser("status")
    preview = sub.add_parser("preview")
    preview.add_argument("drive")
    preview.add_argument("usb_path", type=Path)
    args = parser.parse_args(argv)

    config = load_config(args.config)
    if args.command == "preview" and isinstance(config.get("loadmaster"), dict):
        # A dry run is allowed before Loadmaster is switched on.
        config = {**config, "loadmaster": {**config["loadmaster"], "enabled": True}}
    settings = load_settings(config)
    if settings is None:
        print("Loadmaster is not enabled (loadmaster.enabled in truepanel.yaml).")
        return 2

    if args.command == "status":
        print(json.dumps(read_status(settings.status_path), indent=2, default=str))
        return 0

    if args.command == "preview":
        drive = settings.drive_named(args.drive)
        if drive is None:
            print(f"No drive named {args.drive!r} in truepanel.yaml.")
            return 2
        record = StateStore(settings.state_dir).load_record(drive.key, drive.name)
        plan = build_plan(
            drive_name=drive.name,
            nas=scan(drive.nas_path).files,
            usb=scan(args.usb_path).files,
            record=record.files if record.known else None,
            usb_fstype=_fstype(args.usb_path),
            protected=drive.protected,
            large_delete_files=settings.large_delete_files,
            library=library_index((d.name, d.nas_path) for d in settings.drives),
            usb_folders=folder_keys(args.usb_path),
        )
        s = plan["summary"]
        print(
            f"{drive.name}: {plan['state']}"
            + (f" ({plan['reason']})" if plan["reason"] else "")
            + (" — first sync, nothing will be deleted" if plan["first_sync"] else "")
        )
        print(f"  NAS -> USB   {s['to_usb_files']:6} files  {_size(s['to_usb_bytes'])}")
        print(f"  USB -> NAS   {s['to_nas_files']:6} files  {_size(s['to_nas_bytes'])}")
        print(f"  remove (USB) {s['delete_usb_files']:6} files")
        print(f"  retire (NAS) {s['retire_nas_files']:6} files")
        print(f"  in sync      {s['in_sync_files']:6} files")
        for action in plan["actions"][:200]:
            print(f"  {action['op']:<10} {action['reason']:<34} {action['path']}")
        for item in plan["conflicts"]:
            print(f"  !! {item['reason']:<32} {item['path']}")
        by_reason: dict[str, list[dict]] = {}
        for item in plan["notices"]:
            by_reason.setdefault(item["reason"], []).append(item)
        for reason, items in sorted(by_reason.items()):
            print(f"  !! {reason}: {len(items)} file(s)")
            for item in items[:20]:
                detail = (
                    item.get("would")
                    or item.get("usb_path")
                    or (
                        "already: " + ", ".join(item["other"])
                        if item.get("other")
                        else ""
                    )
                )
                print(f"       {item['path']}" + (f"  ({detail})" if detail else ""))
        return 0

    service = build_service(config)
    done = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: done.set())
    signal.signal(signal.SIGINT, lambda *_: done.set())
    service.start_service()
    print("Loadmaster running; Ctrl-C to stop.", file=sys.stderr)
    done.wait()
    service.stop_service()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
