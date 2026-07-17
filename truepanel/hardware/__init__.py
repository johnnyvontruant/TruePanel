"""
TruePanel hardware support.

Raw controllers expose Linux hardware state. Topology and inventory services
translate that state into the physical machine understood by Mission Control.
"""

from .a125 import A125Capabilities, A125Controller
from .buzzer import Buzzer
from .enclosure import (
    DEFAULT_ENCLOSURE_ROOT,
    EnclosureController,
    EnclosureSlot,
)
from .inventory import (
    DEFAULT_BLOCK_ROOT,
    Drive,
    StorageDevice,
    StorageInventory,
)
from .manager import HardwareManager
from .topology import FrontBay, TopologyResolver

__all__ = [
    "A125Capabilities",
    "A125Controller",
    "Buzzer",
    "DEFAULT_BLOCK_ROOT",
    "DEFAULT_ENCLOSURE_ROOT",
    "Drive",
    "EnclosureController",
    "EnclosureSlot",
    "FrontBay",
    "HardwareManager",
    "StorageDevice",
    "StorageInventory",
    "TopologyResolver",
]


from .health import StorageHealthService
from .smart import SmartctlProvider, parse_smartctl_json
from .telemetry import HealthState, StorageHealthRecord, StorageTelemetry
