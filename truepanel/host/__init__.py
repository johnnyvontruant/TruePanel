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
from .runtime import HostAgentRuntime

__all__ = [
    "HostAgentCapabilities",
    "HostAgentRuntime",
    "HostCapability",
    "capabilities_from_compatibility",
]
