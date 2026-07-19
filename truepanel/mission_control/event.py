from dataclasses import dataclass, field
from typing import Any

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

    # Structured context for specialized renderers, recorders, plugins,
    # notification backends, and future event replay.
    #
    # Existing callers remain compatible because metadata is optional and
    # defaults to an independent empty dictionary for every event.
    metadata: dict[str, Any] = field(default_factory=dict)
