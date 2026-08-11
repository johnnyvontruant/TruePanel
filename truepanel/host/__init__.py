"""
TruePanel host-agent primitives.

The host package defines the boundary between TruePanel applications and
privileged host hardware services.
"""

from .bootstrap import (
    HostAgentBootstrap,
    build_host_agent_bootstrap,
)
from .capabilities import (
    HostAgentCapabilities,
    HostCapability,
    capabilities_from_compatibility,
)
from .factory import build_host_agent_runtime
from .hooks import (
    HostAgentApplicationHooks,
    HostAgentSafetyServices,
)
from .runtime import HostAgentRuntime
from .safety import HostAgentSafetyCoordinator
from .telemetry import HostFanTelemetryProvider
from .thermal_authority import HostThermalAuthority

__all__ = [
    "build_host_agent_bootstrap",
    "HostAgentBootstrap",
    "HostAgentCapabilities",
    "HostAgentApplicationHooks",
    "HostAgentRuntime",
    "HostAgentSafetyCoordinator",
    "HostAgentSafetyServices",
    "HostThermalAuthority",
    "HostCapability",
    "build_host_agent_runtime",
    "capabilities_from_compatibility",
    "HostFanTelemetryProvider",
]

