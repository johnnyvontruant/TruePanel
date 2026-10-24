"""Loadmaster: keep USB drives and NAS media folders in sync with one button.

Plug in a drive, press Copy on the NAS (or Start in TruePanel), unplug when it
says "Safe to remove". See docs/LOADMASTER.md.
"""

from __future__ import annotations

import functools
import logging
from typing import Any

from .config import LoadmasterConfigError, Settings, load_settings

LOGGER = logging.getLogger(__name__)


def build_service(config: dict[str, Any], *, button_reader_factory=None):
    """Return a ready-to-start LoadmasterService, or None when disabled."""

    settings = load_settings(config)
    if settings is None:
        return None

    from .servarr import poll
    from .service import LoadmasterService
    from .state import StateStore

    store = StateStore(settings.state_dir)
    reader, note = None, None
    if not settings.copy_button:
        note = "off in settings"
    else:
        try:
            if button_reader_factory is None:
                from truepanel.hardware.fintek_gpio import FintekCopyButtonReader

                button_reader_factory = FintekCopyButtonReader
            reader = button_reader_factory()
        except Exception as error:  # noqa: BLE001 - run without the button
            LOGGER.warning("Loadmaster Copy button unavailable: %s", error)
            note = f"unavailable: {error}"

    return LoadmasterService(
        settings,
        store=store,
        servarr_poll=functools.partial(poll, settings, store),
        button_reader=reader,
        button_note=note,
    )


__all__ = ["LoadmasterConfigError", "Settings", "build_service", "load_settings"]
