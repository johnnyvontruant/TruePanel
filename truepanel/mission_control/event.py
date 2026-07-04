from dataclasses import dataclass

from .constants import Category, Priority


@dataclass
class MissionEvent:
    priority: Priority
    title: str
    message: str
    category: Category = Category.SYSTEM
    timeout: int = 5
    event_id: str = "system.unknown"
    source: str = "mission_control"
