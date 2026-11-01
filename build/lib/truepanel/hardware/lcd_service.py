"""Application-owned lifecycle helpers for virtual LCD commands."""

from __future__ import annotations

from collections.abc import Callable

from .lcd_command import (
    LCDCommandProcessor,
    LCDCommandServer,
)


def build_lcd_command_server(
    *,
    submit_button: Callable[[int, str], bool] | None,
) -> LCDCommandServer | None:
    """Build the LCD application's guarded virtual-button server."""

    if submit_button is None:
        return None

    return LCDCommandServer(
        LCDCommandProcessor(
            submit_button
        )
    )


__all__ = [
    "build_lcd_command_server",
]
