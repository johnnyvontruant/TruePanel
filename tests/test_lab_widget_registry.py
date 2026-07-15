import pytest

from truepanel.lab.widgets.base import Widget
from truepanel.lab.widgets.registry import (
    WidgetRegistry,
)


class FakeWidget(Widget):
    def render(self, value):
        return ""


def test_register_widget():
    registry = WidgetRegistry()

    registry.register(
        "fake",
        FakeWidget,
    )

    assert "fake" in registry


def test_lookup():
    registry = WidgetRegistry()

    registry.register(
        "fake",
        FakeWidget,
    )

    assert registry.get("fake") is FakeWidget


def test_duplicate_registration():
    registry = WidgetRegistry()

    registry.register(
        "fake",
        FakeWidget,
    )

    with pytest.raises(ValueError):
        registry.register(
            "fake",
            FakeWidget,
        )


def test_unknown_widget():
    registry = WidgetRegistry()

    with pytest.raises(ValueError):
        registry.get("missing")


def test_names_sorted():
    registry = WidgetRegistry()

    registry.register("b", FakeWidget)
    registry.register("a", FakeWidget)

    assert registry.names() == (
        "a",
        "b",
    )


def test_length():
    registry = WidgetRegistry()

    registry.register(
        "fake",
        FakeWidget,
    )

    assert len(registry) == 1
