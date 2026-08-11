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
from .factory import build_host_agent_runtime
from .hooks import HostAgentApplicationHooks
from .runtime import HostAgentRuntime

__all__ = [
    "HostAgentCapabilities",
    "HostAgentApplicationHooks",
    "HostAgentRuntime",
    "HostCapability",
    "build_host_agent_runtime",
    "capabilities_from_compatibility",
]
