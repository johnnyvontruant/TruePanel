"""
TruePanel host-agent primitives.

The host package defines the boundary between TruePanel applications and
privileged host hardware services.
"""

from .capabilities import (
    HostAgentCapabilities,
    HostCapability,
    capabilities_from_compatibility,
)

__all__ = [
    "HostAgentCapabilities",
    "HostCapability",
    "capabilities_from_compatibility",
]
