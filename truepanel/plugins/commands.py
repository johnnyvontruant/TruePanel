"""
Plugin CLI command integration.
"""

from __future__ import annotations

import json
from pathlib import Path

from truepanel.config.loader import load_config

from .administration import (
    install_plugin,
    installed_plugins,
    remove_plugin,
    set_enabled,
    update_plugin,
)
from .api import PLUGIN_API_VERSION
from .manager import load_plugins


def add_plugin_subcommands(subcommands):
    plugins = subcommands.add_parser(
        "plugins",
        help="Manage TruePanel plugins",
    )

    actions = plugins.add_subparsers(dest="plugin_action")

    actions.add_parser("list", help="List loaded plugins")
    actions.add_parser(
        "health",
        help="Show plugin health and load failures",
    )

    inspect_command = actions.add_parser(
        "inspect",
        help="Inspect a plugin",
    )
    inspect_command.add_argument("plugin_id")

    install = actions.add_parser(
        "install",
        help="Install a local plugin",
    )
    install.add_argument("source")

    update = actions.add_parser(
        "update",
        help="Update from the recorded local source",
    )
    update.add_argument("plugin_id")

    remove = actions.add_parser(
        "remove",
        help="Remove an external plugin",
    )
    remove.add_argument("plugin_id")

    enable = actions.add_parser(
        "enable",
        help="Enable an external plugin",
    )
    enable.add_argument("plugin_id")

    disable = actions.add_parser(
        "disable",
        help="Disable an external plugin",
    )
    disable.add_argument("plugin_id")

    validate = actions.add_parser(
        "validate",
        help="Load and validate all plugins",
    )
    validate.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
    )

    return plugins


def print_registry(registry):
    summary = registry.summary()

    print("\nTruePanel Plugin Platform")
    print("=========================")
    print(f"Plugin API: {PLUGIN_API_VERSION}")

    print("\nLoaded Plugins")
    print("--------------")

    for plugin in summary["plugins"]:
        builtin = " [builtin]" if plugin.get("builtin") else ""
        print(
            f"- {plugin['plugin_id']}: "
            f"{plugin['name']} {plugin['version']}{builtin}"
        )

    print("\nCapabilities")
    print("------------")
    print(f"Collectors:      {len(summary['collectors'])}")
    print(f"Dashboard pages: {len(summary['dashboard_pages'])}")
    print(f"Watchers:        {len(summary['watchers'])}")
    print(f"Notifications:   {len(summary['notifications'])}")
    print(f"Theme packs:     {len(summary['theme_packs'])}")

    if summary["disabled_plugins"]:
        print("\nDisabled")
        print("--------")

        for plugin in summary["disabled_plugins"]:
            print(f"- {plugin['plugin_id']}")

    if summary["failed_plugins"]:
        print("\nFailed")
        print("------")

        for plugin in summary["failed_plugins"]:
            print(
                f"- {plugin['plugin_id']}: "
                f"{plugin.get('error', 'unknown error')}"
            )


def print_health(registry):
    summary = registry.summary()
    failed = summary["failed_plugins"]

    print("\nPlugin Health")
    print("=============")

    for result in registry.plugin_results:
        symbol = {
            "loaded": "✓",
            "disabled": "-",
            "failed": "✗",
        }.get(result["status"], "?")

        line = (
            f"{symbol} {result['plugin_id']:<24} "
            f"{result['status']}"
        )

        if result.get("error"):
            line += f" | {result['error']}"

        print(line)

    print()
    print(
        "PLUGIN PLATFORM READY"
        if not failed
        else "PLUGIN PLATFORM DEGRADED"
    )

    return 0 if not failed else 1


def inspect_plugin(registry, plugin_id):
    matches = [
        plugin
        for plugin in registry.plugins
        if plugin["plugin_id"] == plugin_id
    ]

    if not matches:
        results = [
            item
            for item in registry.plugin_results
            if item["plugin_id"] == plugin_id
        ]

        if results:
            print(json.dumps(results[0], indent=2))
            return 0

        print(f"Plugin not found: {plugin_id}")
        return 1

    plugin = matches[0]
    print(json.dumps(plugin, indent=2))

    owned_pages = [
        page
        for page in registry.dashboard_pages
        if page.get("plugin_id") == plugin_id
    ]
    owned_watchers = [
        watcher
        for watcher in registry.watchers
        if watcher.get("plugin_id") == plugin_id
    ]

    print("\nRegistrations")
    print("-------------")
    print(f"Dashboard pages: {len(owned_pages)}")
    print(f"Watchers:        {len(owned_watchers)}")

    return 0


def handle_plugin_command(args):
    if args.command != "plugins":
        return None

    action = getattr(args, "plugin_action", None)

    if action == "install":
        plugin_id, destination = install_plugin(args.source)
        print(f"Installed plugin: {plugin_id}")
        print(f"Location: {destination}")
        print("Restart TruePanel to activate it.")
        return 0

    if action == "update":
        plugin_id, destination = update_plugin(args.plugin_id)
        print(f"Updated plugin: {plugin_id}")
        print(f"Location: {destination}")
        print("Restart TruePanel to activate it.")
        return 0

    if action == "remove":
        remove_plugin(args.plugin_id)
        print(f"Removed plugin: {args.plugin_id}")
        print("Restart TruePanel to apply the change.")
        return 0

    if action == "enable":
        set_enabled(args.plugin_id, True)
        print(f"Enabled plugin: {args.plugin_id}")
        print("Restart TruePanel to activate it.")
        return 0

    if action == "disable":
        set_enabled(args.plugin_id, False)
        print(f"Disabled plugin: {args.plugin_id}")
        print("Restart TruePanel to apply the change.")
        return 0

    config = load_config()
    registry = load_plugins(config)

    if action == "health":
        return print_health(registry)

    if action == "inspect":
        return inspect_plugin(registry, args.plugin_id)

    if action == "validate":
        if args.json_output:
            print(
                json.dumps(
                    registry.summary(),
                    indent=2,
                    default=str,
                )
            )
            return 0 if not registry.failed_plugins else 1

        return print_health(registry)

    print_registry(registry)

    external = installed_plugins()

    if external:
        print("\nInstalled External Plugins")
        print("--------------------------")
        for plugin_id in external:
            print(f"- {plugin_id}")

    return 0
