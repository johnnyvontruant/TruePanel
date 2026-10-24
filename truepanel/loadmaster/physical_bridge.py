"""Fail-closed adapter from the host-owned GPIO75 confirmation to Loadmaster v2.

The host agent remains the only physical button reader. Merely importing or
constructing this adapter does not arm the gate or start a transfer. The host
must arm its existing confirmation gate after independently establishing the
legacy commissioned-baseline/backlog preflight. No second GPIO watcher exists.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from truepanel.cargo.copy_button import CopyButtonConfirmation
from .link import COMMAND_SOCKET, STATUS_PATH, LinkError, read_status, send_command

LOGGER = logging.getLogger(__name__)


class ConfirmationBridge:
    """Consume one host-generated confirmation for an unchanged READY plan."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        status_reader: Callable[[], dict[str, Any]] | None = None,
        sender: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.enabled = enabled
        self.status_reader = status_reader or (lambda: read_status(STATUS_PATH))
        self.sender = sender or (lambda request: send_command(COMMAND_SOCKET, request, timeout=5))
        self._used: set[tuple[str, str, str]] = set()

    def accept(self, confirmation: CopyButtonConfirmation) -> bool:
        """Refuse disabled, stale, changed, removal or mismatched plans."""
        if not self.enabled:
            return False
        if not isinstance(confirmation, CopyButtonConfirmation):
            return False
        try:
            status = self.status_reader()
            if status.get("available") is not True or status.get("state") != "READY":
                return False
            if float(status.get("age", 999)) > 5:
                return False
            drive, plan = status.get("drive") or {}, status.get("plan") or {}
            summary = plan.get("summary") or {}
            if (
                plan.get("state") != "READY"
                or plan.get("needs_confirmation") is not False
                or plan.get("digest") != confirmation.plan_digest
                or drive.get("uuid") != confirmation.cartridge_uuid
                or drive.get("serial") != confirmation.device_serial
                or drive.get("name") != confirmation.cartridge_id
            ):
                return False
            # Physical Copy is strictly NAS -> USB. Never authorize ingestion,
            # replacement/retirement, deletes, or a zero-work plan.
            if (
                int(summary.get("to_usb_files", 0)) < 1
                or int(summary.get("to_usb_bytes", 0)) < 1
                or any(int(summary.get(k, 0)) != 0 for k in (
                    "to_nas_files", "delete_usb_files", "retire_nas_files", "conflicts"
                ))
            ):
                return False
            identity = (confirmation.cartridge_uuid, confirmation.device_serial, confirmation.plan_digest)
            if identity in self._used:
                return False
            # Mark consumed before IPC: a transport failure must not permit a
            # second press to silently replay a potentially accepted command.
            self._used.add(identity)
            result = self.sender({
                "action": "start",
                "source": "host",
                "digest": confirmation.plan_digest,
                "confirm": True,
            })
            return result.get("ok") is True and result.get("status") == "started"
        except (LinkError, OSError, ValueError, TypeError, KeyError) as error:
            LOGGER.warning("Loadmaster physical confirmation refused: %s", error)
            return False


__all__ = ["ConfirmationBridge"]
