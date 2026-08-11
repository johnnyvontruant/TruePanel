"""
Host-owned thermal-control authority state.

This object centralizes the mutable authorization state used by TruePanel's
guarded thermal-control workflow. It composes the existing tested thermal
coordinator and bounded automatic lease primitives rather than replacing them.

Every process starts disarmed and in dry-run mode.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from truepanel.hardware.bounded_automatic import (
    AUTOMATIC_LEASE_SECONDS,
    BoundedAutomaticLease,
)
from truepanel.hardware.thermal_control import (
    ThermalControlCoordinator,
)


class HostThermalAuthority:
    """
    Own ephemeral thermal-control authorization state.

    Configuration may make thermal control available, but construction never
    grants live authority. Each process starts disarmed and dry-run.
    """

    def __init__(
        self,
        *,
        service: Any,
        policy_mode: str,
        command_cooldown_seconds: float,
        current_fingerprint: str,
        commissioned_fingerprint: str,
        automatic_lease_seconds: float = AUTOMATIC_LEASE_SECONDS,
        supervised_session_seconds: float = 120.0,
        clock: Callable[[], float] | None = None,
    ):
        self.clock = clock or time.monotonic

        self.operator_armed = False
        self.dry_run = True

        self.current_recommendation = None
        self.last_result = None

        self.current_fingerprint = str(
            current_fingerprint
        ).strip().lower()

        self.commissioned_fingerprint = str(
            commissioned_fingerprint
        ).strip().lower()

        self.supervised_session_seconds = float(
            supervised_session_seconds
        )

        if self.supervised_session_seconds <= 0:
            raise ValueError(
                "Supervised thermal session must be positive."
            )

        self.supervised_session_deadline: float | None = None

        self.coordinator = ThermalControlCoordinator(
            service,
            policy_mode=policy_mode,
            operator_armed=False,
            dry_run=True,
            command_cooldown_seconds=(
                command_cooldown_seconds
            ),
        )

        self.automatic_lease = BoundedAutomaticLease(
            commissioned_fingerprint=(
                self.commissioned_fingerprint
            ),
            duration_seconds=(
                automatic_lease_seconds
            ),
            clock=self.clock,
        )

    @property
    def policy_mode(self) -> str:
        return self.coordinator.policy_mode

    def supervised_session_active(self) -> bool:
        deadline = self.supervised_session_deadline

        return (
            deadline is not None
            and float(self.clock()) < deadline
        )

    def supervised_session_remaining(self) -> float:
        deadline = self.supervised_session_deadline

        if deadline is None:
            return 0.0

        return max(
            0.0,
            deadline - float(self.clock()),
        )

    def start_supervised_session(self) -> None:
        self.supervised_session_deadline = (
            float(self.clock())
            + self.supervised_session_seconds
        )

    def clear_supervised_session(self) -> bool:
        existed = (
            self.supervised_session_deadline
            is not None
        )

        self.supervised_session_deadline = None

        return existed

    def configure_authority(
        self,
        *,
        operator_armed: bool,
        dry_run: bool | None = None,
    ) -> None:
        self.operator_armed = bool(
            operator_armed
        )

        kwargs = {
            "operator_armed": self.operator_armed,
        }

        if dry_run is not None:
            self.dry_run = bool(dry_run)
            kwargs["dry_run"] = self.dry_run

        self.coordinator.configure(
            **kwargs
        )

    def reset_to_safe_state(self) -> None:
        """
        Reset ephemeral authority without issuing a hardware command.

        Hardware restoration remains the responsibility of the Host Agent
        safety coordinator so state reset cannot bypass guarded restoration.
        """

        self.automatic_lease.cancel()
        self.clear_supervised_session()

        self.operator_armed = False
        self.dry_run = True
        self.last_result = None

        self.coordinator.configure(
            operator_armed=False,
            dry_run=True,
        )

        self.coordinator.simulated_profile = (
            self.coordinator._profile(
                "automatic"
            )
        )

        self.coordinator.owns_control = False


__all__ = [
    "HostThermalAuthority",
]
