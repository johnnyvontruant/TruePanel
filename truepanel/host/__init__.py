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
from .factory import (
    build_host_agent_runtime,
    build_host_agent_runtime_from_bootstrap,
)
from .hooks import (
    HostAgentApplicationHooks,
    HostAgentSafetyServices,
)
from .ownership import (
    DEFAULT_HOST_OWNERSHIP_PATH,
    HostOwnershipError,
    HostOwnershipGuard,
)
from .reconciliation import (
    HostFanReconciliationCoordinator,
)
from .runtime import HostAgentRuntime
from .safety import HostAgentSafetyCoordinator
from .telemetry import HostFanTelemetryProvider
from .thermal_authority import HostThermalAuthority
from .thermal_observer import HostThermalObserver

__all__ = [
    "build_host_agent_bootstrap",
    "HostAgentBootstrap",
    "HostAgentCapabilities",
    "HostAgentApplicationHooks",
    "HostAgentRuntime",
    "HostAgentSafetyCoordinator",
    "HostAgentSafetyServices",
    "HostFanReconciliationCoordinator",
    "HostOwnershipError",
    "HostOwnershipGuard",
    "DEFAULT_HOST_OWNERSHIP_PATH",
    "HostThermalAuthority",
    "HostThermalObserver",
    "HostCapability",
    "build_host_agent_runtime",
    "build_host_agent_runtime_from_bootstrap",
    "capabilities_from_compatibility",
    "HostFanTelemetryProvider",
]
