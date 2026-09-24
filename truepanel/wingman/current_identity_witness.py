"""Typed evidence for an independently observed *current* physical drive identity.

A persisted Lifeline session, a timestamp copied from a status response, or a
model-generated description is never an observation. A future trusted internal
provider must read the current device-to-bay inventory and stable hardware
identity before constructing a witness. This lab module performs no I/O.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

_CURRENT_PROOFS = {
    ("wwn", "udev_wwn_cross_checked_inventory"),
    ("serial_model", "inventory_serial_cross_checked"),
}


@dataclass(frozen=True)
class CurrentDriveWitness:
    """Privacy-safe current observation, independent of the Lifeline ledger."""

    observed_at: float
    pool: str
    vdev: str
    member_id: str
    device: str
    bay: int
    serial_last4: str
    stable_key: str
    mode: str
    source: str
    confidence: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.observed_at, bool)
            or not isinstance(self.observed_at, (float, int))
            or not math.isfinite(self.observed_at)
        ):
            raise ValueError("Witness timestamp must be finite")
        if type(self.bay) is not int or not 1 <= self.bay <= 999:
            raise ValueError("Witness bay must be an integer 1..999")
        if any(
            not isinstance(value, str) or not value.strip() or len(value) > 128
            for value in (
                self.pool,
                self.vdev,
                self.member_id,
                self.device,
                self.serial_last4,
                self.stable_key,
                self.mode,
                self.source,
                self.confidence,
            )
        ):
            raise ValueError("Witness requires bounded nonempty identity fields")
        if (self.mode, self.source) not in _CURRENT_PROOFS:
            raise ValueError("Historical and fallback identities are not live proof")
        if self.confidence not in {"high", "very_high"}:
            raise ValueError("Witness confidence is insufficient")


__all__ = ["CurrentDriveWitness"]
