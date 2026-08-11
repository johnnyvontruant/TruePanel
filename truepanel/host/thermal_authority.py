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


    def handle_action(
        self,
        action,
        *,
        telemetry_provider,
        runtime_status_provider,
        restore_automatic,
        record_commissioning_event,
    ):
        """Apply a guarded runtime arm-state change.

        This first operator workflow intentionally supports dry-run only.
        Live thermal actuation remains locked out until separately enabled
        and reviewed.
        """


        normalized = str(
            action
        ).strip().lower()

        if normalized not in {
            "arm",
            "disarm",
            "supervised_live",
            "automatic_lease",
            "automatic_lease_renew",
        }:
            return {
                "ok": False,
                "status": "invalid_action",
                "message": (
                    "Thermal-control action must be arm, disarm, "
                    "supervised_live, automatic_lease, or "
                    "automatic_lease_renew."
                ),
            }

        if self.policy_mode != "automatic_control":
            return {
                "ok": False,
                "status": "wrong_mode",
                "message": (
                    "Thermal policy mode must be "
                    "automatic_control."
                ),
                "policy_mode": self.policy_mode,
            }

        if (
            normalized == "arm"
            and not self.dry_run
        ):
            return {
                "ok": False,
                "status": "live_control_locked",
                "message": (
                    "Standard runtime arming is limited "
                    "to dry-run mode."
                ),
                "dry_run": False,
            }

        telemetry = telemetry_provider()
        runtime_status = (
            runtime_status_provider()
        )

        if normalized == "automatic_lease":
            recommendation_profile = (
                self.current_recommendation
                .recommended_profile
                .value
                if self.current_recommendation is not None
                else "automatic"
            )

            lease_decision = self.automatic_lease.start(
                current_fingerprint=(
                    self.current_fingerprint
                ),
                active_profile=runtime_status.get(
                    "active_profile",
                    "automatic",
                ),
                recommended_profile=(
                    recommendation_profile
                ),
                telemetry_valid=bool(
                    self.current_recommendation is not None
                    and self.current_recommendation
                    .telemetry_valid
                ),
                telemetry_fresh=bool(
                    telemetry.get(
                        "telemetry_fresh",
                        False,
                    )
                ),
                connected=bool(
                    runtime_status.get(
                        "connected",
                        False,
                    )
                ),
                safety_hold=bool(
                    runtime_status.get(
                        "safety_hold",
                        False,
                    )
                ),
                recovery_pending=bool(
                    runtime_status.get(
                        "recovery_pending",
                        False,
                    )
                ),
            )

            if not lease_decision.accepted:
                return {
                    "ok": False,
                    "status": lease_decision.status,
                    "message": lease_decision.message,
                    "blocking_reasons": list(
                        lease_decision.blocking_reasons
                    ),
                    "operator_armed": (
                        self.operator_armed
                    ),
                    "dry_run": self.dry_run,
                    "automatic_lease_active": False,
                }

            self.operator_armed = True

            self.coordinator.configure(
                operator_armed=True,
                dry_run=False,
            )

        elif normalized == "automatic_lease_renew":
            recommendation_profile = (
                self.current_recommendation
                .recommended_profile
                .value
                if self.current_recommendation is not None
                else "automatic"
            )

            lease_decision = self.automatic_lease.renew(
                current_fingerprint=(
                    self.current_fingerprint
                ),
                active_profile=runtime_status.get(
                    "active_profile",
                    "automatic",
                ),
                recommended_profile=(
                    recommendation_profile
                ),
                telemetry_valid=bool(
                    self.current_recommendation is not None
                    and self.current_recommendation
                    .telemetry_valid
                ),
                telemetry_fresh=bool(
                    telemetry.get(
                        "telemetry_fresh",
                        False,
                    )
                ),
                connected=bool(
                    runtime_status.get(
                        "connected",
                        False,
                    )
                ),
                safety_hold=bool(
                    runtime_status.get(
                        "safety_hold",
                        False,
                    )
                ),
                recovery_pending=bool(
                    runtime_status.get(
                        "recovery_pending",
                        False,
                    )
                ),
            )

            if not lease_decision.accepted:
                return {
                    "ok": False,
                    "status": lease_decision.status,
                    "message": lease_decision.message,
                    "blocking_reasons": list(
                        lease_decision.blocking_reasons
                    ),
                    "operator_armed": (
                        self.operator_armed
                    ),
                    "dry_run": self.dry_run,
                    "automatic_lease_active": (
                        self.automatic_lease.active()
                    ),
                    "automatic_lease_remaining": (
                        self.automatic_lease
                        .remaining_seconds()
                    ),
                }

            self.operator_armed = True

            self.coordinator.configure(
                operator_armed=True,
                dry_run=False,
            )

        elif normalized == "supervised_live":
            blocking_reasons = []

            if not self.dry_run:
                blocking_reasons.append(
                    "The supervised session must begin "
                    "from dry-run mode."
                )

            if self.current_recommendation is None:
                blocking_reasons.append(
                    "Thermal recommendation is unavailable."
                )
            elif not bool(
                self.current_recommendation
                .telemetry_valid
            ):
                blocking_reasons.append(
                    "Thermal recommendation telemetry "
                    "is invalid."
                )
            elif (
                self.current_recommendation
                .recommended_profile
                .value
                != "balanced"
            ):
                blocking_reasons.append(
                    "Supervised live control permits "
                    "only the balanced recommendation."
                )

            if not bool(
                telemetry.get(
                    "telemetry_fresh",
                    False,
                )
            ):
                blocking_reasons.append(
                    "Thermal telemetry is stale."
                )

            if not bool(
                runtime_status.get(
                    "connected",
                    False,
                )
            ):
                blocking_reasons.append(
                    "Fan-control runtime is disconnected."
                )

            if (
                runtime_status.get(
                    "active_profile"
                )
                != "automatic"
            ):
                blocking_reasons.append(
                    "Supervised live control must begin "
                    "from motherboard automatic mode."
                )

            if bool(
                runtime_status.get(
                    "safety_hold",
                    False,
                )
            ):
                blocking_reasons.append(
                    "Fan-control safety hold is active."
                )

            if bool(
                runtime_status.get(
                    "recovery_pending",
                    False,
                )
            ):
                blocking_reasons.append(
                    "Fan-control safety recovery is pending."
                )

            fan_channels = (
                telemetry
                .get("fan_status", {})
                .get("fan_channels", [])
            )

            controlled = {
                int(item.get("number")): item
                for item in fan_channels
                if isinstance(item, dict)
                and item.get("number") in (1, 2)
            }

            for channel in (1, 2):
                item = controlled.get(channel)

                if item is None:
                    blocking_reasons.append(
                        f"Controlled fan {channel} "
                        "telemetry is unavailable."
                    )
                    continue

                try:
                    rpm = float(
                        item.get("rpm", 0)
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    rpm = 0.0

                if rpm < 300:
                    blocking_reasons.append(
                        f"Controlled fan {channel} "
                        "is below the safe RPM floor."
                    )

                if bool(
                    item.get("alarm", False)
                ):
                    blocking_reasons.append(
                        f"Controlled fan {channel} "
                        "reports an alarm."
                    )

            if blocking_reasons:
                return {
                    "ok": False,
                    "status": "readiness_blocked",
                    "message": blocking_reasons[0],
                    "blocking_reasons": blocking_reasons,
                    "operator_armed": (
                        self.operator_armed
                    ),
                    "dry_run": self.dry_run,
                }

            self.operator_armed = True

            self.coordinator.configure(
                operator_armed=True,
                dry_run=False,
            )

            self.supervised_session_deadline = (
                self.clock()
                + self.supervised_session_seconds
            )

        elif normalized == "arm":
            blocking_reasons = []

            if self.current_recommendation is None:
                blocking_reasons.append(
                    "Thermal recommendation is unavailable."
                )
            elif not bool(
                self.current_recommendation
                .telemetry_valid
            ):
                blocking_reasons.append(
                    "Thermal recommendation telemetry "
                    "is invalid."
                )

            if not bool(
                telemetry.get(
                    "telemetry_fresh",
                    False,
                )
            ):
                blocking_reasons.append(
                    "Thermal telemetry is stale."
                )

            if not bool(
                runtime_status.get(
                    "connected",
                    False,
                )
            ):
                blocking_reasons.append(
                    "Fan-control runtime is disconnected."
                )

            if bool(
                runtime_status.get(
                    "safety_hold",
                    False,
                )
            ):
                blocking_reasons.append(
                    "Fan-control safety hold is active."
                )

            if blocking_reasons:
                return {
                    "ok": False,
                    "status": "readiness_blocked",
                    "message": blocking_reasons[0],
                    "blocking_reasons": (
                        blocking_reasons
                    ),
                    "operator_armed": (
                        self.operator_armed
                    ),
                    "dry_run": self.dry_run,
                }

            self.operator_armed = True
            self.coordinator.configure(
                operator_armed=True
            )

        else:
            was_supervised = (
                self.supervised_session_deadline
                is not None
            )
            was_automatic_lease = (
                self.automatic_lease.deadline
                is not None
            )

            self.automatic_lease.cancel()
            self.supervised_session_deadline = None
            self.operator_armed = False

            restore_automatic(
                (
                    "Automatic thermal control disarmed; "
                    "motherboard control restored."
                ),
                telemetry=telemetry,
            )

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
            self.last_result = None

            if was_automatic_lease:
                record_commissioning_event(
                    "automatic_lease_cancelled",
                    (
                        "Bounded automatic thermal control "
                        "manually cancelled; motherboard "
                        "control restored."
                    ),
                    lease_remaining=0.0,
                )

            if was_supervised:
                record_commissioning_event(
                    "supervised_disarmed",
                    (
                        "Automatic thermal control "
                        "manually disarmed; motherboard "
                        "control restored."
                    ),
                    lease_remaining=0.0,
                )

        if (
            normalized != "disarm"
            and self.current_recommendation is not None
        ):
            self.last_result = (
                self.coordinator
                .evaluate(
                    self.current_recommendation,
                    telemetry=telemetry,
                    runtime_status=runtime_status,
                )
            )

        if (
            normalized == "automatic_lease"
            and self.automatic_lease.active()
        ):
            record_commissioning_event(
                "automatic_lease_started",
                (
                    "Bounded automatic thermal control "
                    "engaged for 86400 seconds with balanced "
                    "and cooling boost profiles only."
                ),
                lease_remaining=AUTOMATIC_LEASE_SECONDS,
            )

        if (
            normalized == "automatic_lease_renew"
            and self.automatic_lease.active()
        ):
            record_commissioning_event(
                "automatic_lease_renewed",
                (
                    "Stage 3 automatic thermal control "
                    "renewed for 86400 seconds."
                ),
                lease_remaining=AUTOMATIC_LEASE_SECONDS,
            )

        if (
            normalized == "supervised_live"
            and self.supervised_session_active()
        ):
            record_commissioning_event(
                "supervised_started",
                (
                    "Supervised live thermal control "
                    "engaged for 120 seconds with the "
                    "balanced profile only."
                ),
                lease_remaining=(
                    self.supervised_session_seconds
                ),
            )

        return {
            "ok": True,
            "status": (
                "automatic_lease_renewed"
                if (
                    normalized == "automatic_lease_renew"
                    and self.operator_armed
                )
                else (
                    "automatic_lease"
                    if (
                        normalized == "automatic_lease"
                        and self.operator_armed
                    )
                else (
                    "supervised_live"
                    if (
                        normalized == "supervised_live"
                        and self.operator_armed
                    )
                    else (
                        "armed"
                        if self.operator_armed
                        else "disarmed"
                    )
                )
            )
            ),
            "message": (
                (
                    "Stage 3 automatic thermal control "
                    "renewed for 86400 seconds."
                )
                if (
                    normalized == "automatic_lease_renew"
                    and self.operator_armed
                )
                else (
                (
                    "Bounded automatic thermal control "
                    "engaged for 86400 seconds with balanced "
                    "and cooling boost profiles only."
                )
                if (
                    normalized == "automatic_lease"
                    and self.operator_armed
                )
                else (
                    (
                        "Supervised live thermal control "
                        "engaged for 120 seconds with the "
                        "balanced profile only."
                    )
                    if (
                        normalized == "supervised_live"
                        and self.operator_armed
                    )
                    else (
                        "Automatic thermal control armed "
                        "in dry-run mode."
                        if self.operator_armed
                        else (
                            "Automatic thermal control disarmed; "
                            "motherboard control restored."
                        )
                    )
                )
            )
            ),
            "operator_armed": (
                self.operator_armed
            ),
            "dry_run": (
                self.coordinator.dry_run
            ),
            "policy_mode": self.policy_mode,
            "supervised_session_active": (
                self.supervised_session_active()
            ),
            "supervised_session_seconds": (
                self.supervised_session_seconds
                if self.supervised_session_active()
                else 0.0
            ),
            "automatic_lease_active": (
                self.automatic_lease.active()
            ),
            "automatic_lease_seconds": (
                AUTOMATIC_LEASE_SECONDS
                if self.automatic_lease.active()
                else 0.0
            ),
            "automatic_lease_remaining": (
                self.automatic_lease
                .remaining_seconds()
            ),
            "simulated_profile": (
                self.coordinator
                .simulated_profile
                .value
            ),
        }

__all__ = [
    "HostThermalAuthority",
]
