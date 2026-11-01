"""
Guaranteed restoration support for live protocol experiments.
"""

from __future__ import annotations

from dataclasses import dataclass


DEFAULT_RESTORE_PACKET = b"\x4D\x0D"


@dataclass(frozen=True)
class RestoreResult:
    attempted: bool
    succeeded: bool
    packet: bytes
    error: str = ""

    @property
    def packet_hex(self):
        return self.packet.hex(" ").upper()

    def as_dict(self):
        return {
            "attempted": self.attempted,
            "succeeded": self.succeeded,
            "packet": list(self.packet),
            "packet_hex": self.packet_hex,
            "error": self.error,
        }


class ProtocolRestorer:
    def __init__(
        self,
        sender,
        *,
        fallback_packet=DEFAULT_RESTORE_PACKET,
    ):
        if not callable(sender):
            raise TypeError(
                "sender must be callable"
            )

        self.sender = sender
        self.fallback_packet = bytes(
            fallback_packet
        )

    def restore(self, packet=None):
        payload = bytes(
            packet or self.fallback_packet
        )

        try:
            self.sender(payload)

            return RestoreResult(
                attempted=True,
                succeeded=True,
                packet=payload,
            )

        except Exception as error:
            return RestoreResult(
                attempted=True,
                succeeded=False,
                packet=payload,
                error=str(error),
            )
