"""Shared read-only labels for network interfaces."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

NETWORK_CLASS_ROOT = Path("/sys/class/net")


def physical_interface_positions(
    network_root: Path = NETWORK_CLASS_ROOT,
) -> dict[str, int]:
    """Return stable one-based positions for physical interfaces."""

    try:
        names = sorted(
            entry.name
            for entry in network_root.iterdir()
            if (
                entry.name != "lo"
                and (entry / "device").exists()
            )
        )
    except OSError:
        return {}

    return {
        name: position
        for position, name in enumerate(
            names,
            start=1,
        )
    }


def friendly_network_label(
    name: str,
    positions: Mapping[str, int],
) -> str:
    """Return an operator-facing label without hiding unknown names."""

    if name.startswith("tailscale"):
        return "Tailscale"

    position = positions.get(name)

    if position is None:
        return name

    return f"Ethernet Port {position}"
