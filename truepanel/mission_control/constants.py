from truepanel import __version__
from enum import Enum, IntEnum


MISSION_CONTROL_VERSION = __version__


class Priority(IntEnum):
    NONE = 0
    HEALTHY = 10
    INFO = 40
    WARNING = 70
    CRITICAL = 100


class Category(str, Enum):
    HEALTH = "health"
    STORAGE = "storage"
    THERMAL = "thermal"
    NETWORK = "network"
    SYSTEM = "system"
