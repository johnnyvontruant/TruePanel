"""Fail-closed physical Copy-button confirmation for Loadmaster.

This module does not mount media, copy files, or mutate USB state. It turns one
debounced active-low physical button edge into a one-shot confirmation only
after a caller has independently proven the complete Loadmaster physical
preflight: exact cartridge identity, commissioned baseline, durable backlog,
and a READY backlog-scoped NAS-to-USB plan.

The TVS-671 Copy button was characterized on 2026-10-04 as Fintek GPIO75
(bank 7, bit 5), active-low. Hardware access is deliberately abstracted behind
read_level so tests and future Host-Agent ownership do not need direct
Super-I/O access here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from time import monotonic
from typing import Callable

COPY_BUTTON_BANK = 7
COPY_BUTTON_BIT = 5
COPY_BUTTON_ACTIVE_LOW = True

DEFAULT_DEBOUNCE_SECONDS = 0.075
DEFAULT_REARM_SECONDS = 0.750
DEFAULT_CONFIRMATION_WINDOW_SECONDS = 30.0


@dataclass(frozen=True)
class LoadmasterPhysicalPreflight:
    """Evidence required before a Copy press can authorize one transfer run."""

    cartridge_id: str
    cartridge_uuid: str
    device_serial: str
    plan_state: str
    backup_files: int
    backup_bytes: int
    baseline_verified: bool
    identity_verified: bool
    backlog_verified: bool
    plan_digest: str
    generated_at_monotonic: float

    @property
    def ready(self) -> bool:
        return (
            bool(self.cartridge_id)
            and bool(self.cartridge_uuid)
            and bool(self.device_serial)
            and self.plan_state == "READY"
            and self.backup_files > 0
            and self.backup_bytes > 0
            and self.baseline_verified
            and self.identity_verified
            and self.backlog_verified
            and bool(self.plan_digest)
        )


@dataclass(frozen=True)
class CopyButtonConfirmation:
    """One accepted physical confirmation event."""

    cartridge_id: str
    cartridge_uuid: str
    device_serial: str
    plan_digest: str
    confirmed_at_monotonic: float
    source: str = "fintek_gpio75"
    bank: int = COPY_BUTTON_BANK
    bit: int = COPY_BUTTON_BIT
    active_low: bool = COPY_BUTTON_ACTIVE_LOW

    def public_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload.pop("device_serial", None)
        return payload


class LoadmasterCopyButtonGate:
    """Debounce GPIO75 and issue at most one confirmation per armed preflight."""

    def __init__(
        self,
        *,
        read_level: Callable[[], int | bool],
        clock: Callable[[], float] = monotonic,
        debounce_seconds: float = DEFAULT_DEBOUNCE_SECONDS,
        rearm_seconds: float = DEFAULT_REARM_SECONDS,
        confirmation_window_seconds: float = DEFAULT_CONFIRMATION_WINDOW_SECONDS,
        active_low: bool = COPY_BUTTON_ACTIVE_LOW,
    ) -> None:
        if debounce_seconds <= 0:
            raise ValueError("debounce_seconds must be positive")
        if rearm_seconds <= 0:
            raise ValueError("rearm_seconds must be positive")
        if confirmation_window_seconds <= 0:
            raise ValueError("confirmation_window_seconds must be positive")

        self._read_level = read_level
        self._clock = clock
        self.debounce_seconds = float(debounce_seconds)
        self.rearm_seconds = float(rearm_seconds)
        self.confirmation_window_seconds = float(confirmation_window_seconds)
        self.active_low = bool(active_low)

        self._armed: LoadmasterPhysicalPreflight | None = None
        self._armed_at: float | None = None
        self._candidate_pressed: bool | None = None
        self._candidate_since: float | None = None
        self._stable_pressed = False
        self._last_confirmation_at: float | None = None
        self._consumed_digest: str | None = None

    def arm(self, preflight: LoadmasterPhysicalPreflight) -> None:
        """Arm only a complete READY preflight; otherwise fail closed."""
        if not preflight.ready:
            raise ValueError("Loadmaster physical preflight is not READY")

        now = self._clock()
        age = now - preflight.generated_at_monotonic
        if age < 0 or age > self.confirmation_window_seconds:
            raise ValueError("Loadmaster physical preflight is stale")

        if self._consumed_digest == preflight.plan_digest:
            raise ValueError("Loadmaster physical preflight was already consumed")

        self._armed = preflight
        self._armed_at = now

    def disarm(self) -> None:
        self._armed = None
        self._armed_at = None

    def armed_snapshot(self) -> dict[str, object]:
        preflight = self._armed
        if preflight is None:
            return {
                "armed": False,
                "source": "fintek_gpio75",
                "bank": COPY_BUTTON_BANK,
                "bit": COPY_BUTTON_BIT,
                "active_low": self.active_low,
            }

        return {
            "armed": True,
            "source": "fintek_gpio75",
            "bank": COPY_BUTTON_BANK,
            "bit": COPY_BUTTON_BIT,
            "active_low": self.active_low,
            "cartridge_id": preflight.cartridge_id,
            "cartridge_uuid": preflight.cartridge_uuid,
            "plan_digest": preflight.plan_digest,
            "backup_files": preflight.backup_files,
            "backup_bytes": preflight.backup_bytes,
        }

    def poll(self) -> CopyButtonConfirmation | None:
        """Poll one hardware level and return an accepted press, if any."""
        now = self._clock()
        level = self._read_level()

        if isinstance(level, bool):
            normalized = int(level)
        elif isinstance(level, int) and level in (0, 1):
            normalized = level
        else:
            raise ValueError("Copy button reader must return level 0 or 1")

        pressed = normalized == 0 if self.active_low else normalized == 1

        if self._candidate_pressed is None or pressed != self._candidate_pressed:
            self._candidate_pressed = pressed
            self._candidate_since = now
            return None

        if self._candidate_since is None:
            self._candidate_since = now
            return None

        if now - self._candidate_since < self.debounce_seconds:
            return None

        if pressed == self._stable_pressed:
            return None

        self._stable_pressed = pressed

        if not pressed:
            return None

        preflight = self._armed
        armed_at = self._armed_at

        if preflight is None or armed_at is None:
            return None

        if now - armed_at > self.confirmation_window_seconds:
            self.disarm()
            return None

        if (
            self._last_confirmation_at is not None
            and now - self._last_confirmation_at < self.rearm_seconds
        ):
            return None

        if self._consumed_digest == preflight.plan_digest:
            return None

        confirmation = CopyButtonConfirmation(
            cartridge_id=preflight.cartridge_id,
            cartridge_uuid=preflight.cartridge_uuid,
            device_serial=preflight.device_serial,
            plan_digest=preflight.plan_digest,
            confirmed_at_monotonic=now,
            active_low=self.active_low,
        )

        self._last_confirmation_at = now
        self._consumed_digest = preflight.plan_digest
        return confirmation


__all__ = [
    "COPY_BUTTON_ACTIVE_LOW",
    "COPY_BUTTON_BANK",
    "COPY_BUTTON_BIT",
    "CopyButtonConfirmation",
    "DEFAULT_CONFIRMATION_WINDOW_SECONDS",
    "DEFAULT_DEBOUNCE_SECONDS",
    "DEFAULT_REARM_SECONDS",
    "LoadmasterCopyButtonGate",
    "LoadmasterPhysicalPreflight",
]