"""
Widget registry for Project Stargate.

Provides a central lookup for reusable LCD widgets.
"""

from __future__ import annotations

from typing import Type

from truepanel.lab.widgets.base import Widget


class WidgetRegistry:
    def __init__(self):
        self._widgets: dict[str, Type[Widget]] = {}

    def register(
        self,
        name: str,
        widget: Type[Widget],
    ) -> None:
        if name in self._widgets:
            raise ValueError(
                f"Widget '{name}' already registered"
            )

        self._widgets[name] = widget

    def get(
        self,
        name: str,
    ) -> Type[Widget]:
        try:
            return self._widgets[name]
        except KeyError:
            raise ValueError(
                f"Unknown widget '{name}'"
            )

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._widgets))

    def __contains__(self, name: str):
        return name in self._widgets

    def __len__(self):
        return len(self._widgets)


registry = WidgetRegistry()
