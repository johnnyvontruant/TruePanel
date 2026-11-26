"""``truepanel modules``: read-only module commands.

This release only reports. Installing and removing modules arrives with
the module helper in a later 2.0 pull request.
"""

from __future__ import annotations

import json

from truepanel.config.loader import load_config

from .catalog import CATALOG, TIER_LABELS, TIERS, get_module, validate_catalog
from .selection import selection_from_config


def add_module_subcommands(subcommands):
    modules = subcommands.add_parser(
        "modules",
        help="List TruePanel modules and what each one adds",
    )
    modules.add_argument(
        "--config",
        dest="modules_config",
        default="truepanel.yaml",
        help="Configuration file to read (default: truepanel.yaml)",
    )
    actions = modules.add_subparsers(dest="modules_action")

    listing = actions.add_parser("list", help="List modules and their status")
    listing.add_argument(
        "--json", action="store_true", dest="modules_json", help="Output JSON"
    )
    listing.add_argument(
        "--developer",
        action="store_true",
        dest="modules_developer",
        help="Include developer modules",
    )

    show = actions.add_parser("show", help="Describe one module")
    show.add_argument("module_id")
    show.add_argument(
        "--json", action="store_true", dest="modules_json", help="Output JSON"
    )

    actions.add_parser("validate", help="Check the module catalog")


def _status(selection, module):
    if module.id not in selection.installed:
        return "available"
    if not module.removable:
        return "core"
    return "installed"


def _list(args, selection) -> int:
    show_developer = args.modules_developer or args.modules_json
    if args.modules_json:
        payload = {
            "legacy": selection.legacy,
            "unknown": list(selection.unknown),
            "modules": [
                {
                    **module.to_dict(),
                    "status": _status(selection, module),
                    "auto_added": selection.auto_added.get(module.id),
                }
                for module in CATALOG
            ],
        }
        print(json.dumps(payload, indent=2))
        return 0

    print("TruePanel modules")
    if selection.legacy:
        print(
            "  No modules: section in the configuration yet, so every\n"
            "  feature stays installed exactly as before."
        )
    for tier in TIERS:
        if tier == "developer" and not show_developer:
            continue
        print()
        print(f"{TIER_LABELS[tier]}")
        for module in CATALOG:
            if module.tier != tier:
                continue
            status = _status(selection, module)
            mark = {"core": "[core]", "installed": "[ on ]", "available": "[    ]"}
            line = f"  {mark[status]} {module.id:<18} {module.summary}"
            reason = selection.auto_added.get(module.id)
            if reason:
                line += f" (added: {reason})"
            print(line)
    if not show_developer:
        print("\nDeveloper modules hidden; add --developer to show them.")
    for module_id in selection.unknown:
        print(f"\nIgnored unknown module in configuration: {module_id}")
    return 0


def _show(args, selection) -> int:
    try:
        module = get_module(args.module_id)
    except KeyError as error:
        print(error.args[0])
        return 2
    if args.modules_json:
        print(
            json.dumps(
                {**module.to_dict(), "status": _status(selection, module)},
                indent=2,
            )
        )
        return 0
    print(f"{module.name}  ({module.id} v{module.version})")
    print(f"Tier:   {TIER_LABELS[module.tier]}")
    print(f"Status: {_status(selection, module)}")
    print()
    print(module.description)
    for title, items in (
        ("Adds", module.adds),
        ("Requires modules", module.requires),
        ("Needs", module.needs),
    ):
        if items:
            print(f"\n{title}:")
            for item in items:
                print(f"  - {item}")
    return 0


def handle_module_command(args) -> int:
    action = getattr(args, "modules_action", None) or "list"
    if action == "validate":
        problems = validate_catalog()
        for problem in problems:
            print(problem)
        print("Module catalog OK" if not problems else "Module catalog has problems")
        return 1 if problems else 0

    selection = selection_from_config(load_config(args.modules_config))
    if action == "show":
        return _show(args, selection)
    if not hasattr(args, "modules_json"):
        args.modules_json = False
        args.modules_developer = False
    return _list(args, selection)
