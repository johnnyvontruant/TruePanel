from enum import Enum, IntEnum


MISSION_CONTROL_VERSION = "0.7.0-dev"


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
