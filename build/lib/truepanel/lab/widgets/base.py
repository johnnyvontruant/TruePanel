"""
Project Stargate Widget Framework.

All LCD widgets derive from Widget and expose a common rendering API.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class Widget(ABC):
    """Base class for all LCD widgets."""

    width: int = 16

    def __post_init__(self):
        if self.width < 1:
            raise ValueError(
                "width must be at least 1"
            )

    @abstractmethod
    def render(self, value):
        """Render the widget."""

    @property
    def name(self) -> str:
        return self.__class__.__name__
