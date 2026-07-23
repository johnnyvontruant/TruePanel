#!/usr/bin/env python3
"""
TruePanel Fan Control Phase 6 safety drill.

Exercises the real fan-control service, safety interlock, status bridge,
history event formatter, and LCD page formatter without accessing hardware.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )

from truepanel.hardware.fan_control import (
    FanControlInterlock,
    FanProfile,
)
from truepanel.hardware.fan_service import (
    FanControlService,
)
from truepanel.hardware.fan_status_bridge import (
    FanControlStatusBridge,
)
from truepanel.history.fan_control import (
    FanControlHistory,
    event_from_decision,
)
from truepanel.pages.fans import (
    fan_control_page,
)


class DrillFailure(RuntimeError):
    pass


class DrillClock:
    def __init__(
        self,
        value: float = 1000.0,
    ):
        self.value = float(
            value
        )

    def __call__(self) -> float:
        return self.value

    def advance(
        self,
        seconds: float = 1.0,
    ) -> None:
        self.value += float(
            seconds
        )


class RecordingExecutor:
    """Records decisions without touching any fan controller."""

    def __init__(self):
        self.decisions = []
        self.closed = False

    def apply(
        self,
        decision,
    ) -> None:
        if self.closed:
            raise RuntimeError(
                "Simulation executor is closed."
            )

        self.decisions.append(
            decision
        )

    def close(self) -> None:
        self.closed = True


def fan_status() -> dict:
    return {
        "fan_channels": [
            {
                "number": 1,
                "rpm": 1577,
                "pwm": 174,
                "pwm_mode": "Auto",
                "alarm": False,
            },
            {
                "number": 2,
                "rpm": 1516,
                "pwm": 174,
                "pwm_mode": "Auto",
                "alarm": False,
            },
        ]
    }


def telemetry(
    temperatures_c,
) -> dict:
    return {
        "fan_status": fan_status(),
        "temperatures_c": tuple(
            temperatures_c
        ),
        "telemetry_fresh": True,
    }


def source_for_decision(
    decision,
) -> str:
    reason = str(
        decision.reason
    ).lower()

    if (
        decision.force_automatic
        and "safety recovery confirmed"
        in reason
    ):
        return "recovery"

    if (
        decision.force_automatic
        and "expired" in reason
    ):
        return "timeout"

    return "safety"


def require(
    condition,
    message: str,
) -> None:
    if not condition:
        raise DrillFailure(
            message
        )


def report(
    label: str,
    detail: str = "",
) -> None:
    print(
        f"{label:<38} PASS"
        + (
            f"  {detail}"
            if detail
            else ""
        )
    )


def publish_status(
    bridge,
    service,
):
    status = service.status()

    payload = {
        "enabled": True,
        "connected": True,
        "active_profile": (
            status.active_profile.value
        ),
        "requested_profile": (
            status.requested_profile.value
        ),
        "remaining_seconds": (
            status.remaining_seconds
        ),
        "last_reason": (
            status.last_reason
        ),
        "control_authority": (
            status.control_authority
        ),
        "safety_hold": (
            status.safety_hold
        ),
        "recovery_pending": (
            status.recovery_pending
        ),
        "recovery_healthy_cycles": (
            status.recovery_healthy_cycles
        ),
        "recovery_required_cycles": (
            status.recovery_required_cycles
        ),
    }

    bridge.publish(
        payload
    )

    return bridge.read(
        max_age=30.0
    )


def record_decision(
    history,
    decision,
    temperatures_c,
    *,
    source,
    timestamp,
) -> None:
    history.append(
        event_from_decision(
            decision,
            source=source,
            telemetry=telemetry(
                temperatures_c
            ),
            timestamp=timestamp,
        )
    )


def main() -> int:
    print(
        "TruePanel Fan Control Phase 6"
    )
    print(
        "Simulation-only controlled safety drill"
    )
    print(
        "Hardware access: DISABLED"
    )
    print()

    clock = DrillClock()
    executor = RecordingExecutor()

    with tempfile.TemporaryDirectory(
        prefix="truepanel-fan-drill-"
    ) as temporary_directory:
        temporary = Path(
            temporary_directory
        )

        bridge = FanControlStatusBridge(
            temporary
            / "fan-control-status.json",
            clock=clock,
        )
        history = FanControlHistory(
            temporary
            / "fan-control.jsonl",
            clock=clock,
            compact_every=1000,
        )

        service = FanControlService(
            FanControlInterlock(),
            executor,
            command_timeout=300,
            afterburners_timeout=120,
            safety_recovery_cycles=3,
            clock=clock,
        )

        try:
            baseline = publish_status(
                bridge,
                service,
            )

            require(
                baseline is not None,
                "Baseline bridge status was unavailable.",
            )
            require(
                baseline["active_profile"]
                == "automatic",
                "Baseline was not Automatic.",
            )
            require(
                fan_control_page(
                    baseline
                )
                == [
                    "FAN CONTROL",
                    "AUTOMATIC",
                ],
                "Baseline LCD page was incorrect.",
            )

            report(
                "PHASE 1  Automatic baseline"
            )

            manual = service.request_profile(
                FanProfile.AFTERBURNERS,
                fan_status=fan_status(),
                temperatures_c=(45,),
            )

            record_decision(
                history,
                manual,
                (45,),
                source="manual",
                timestamp=clock(),
            )

            manual_status = publish_status(
                bridge,
                service,
            )

            require(
                manual.accepted,
                "Manual Afterburners was rejected.",
            )
            require(
                manual_status[
                    "control_authority"
                ]
                == "manual",
                "Manual authority was not reported.",
            )
            require(
                manual_status[
                    "remaining_seconds"
                ]
                is not None,
                "Manual deadman timer was missing.",
            )

            report(
                "PHASE 2  Manual Afterburners"
            )

            clock.advance()

            safety = service.tick(
                fan_status=fan_status(),
                temperatures_c=(76,),
            )

            require(
                safety is not None,
                "Safety escalation produced no decision.",
            )

            record_decision(
                history,
                safety,
                (76,),
                source=source_for_decision(
                    safety
                ),
                timestamp=clock(),
            )

            safety_status = publish_status(
                bridge,
                service,
            )

            require(
                safety_status[
                    "control_authority"
                ]
                == "safety",
                "Safety did not assume authority.",
            )
            require(
                safety_status[
                    "safety_hold"
                ]
                is True,
                "Safety hold was not active.",
            )
            require(
                fan_control_page(
                    safety_status
                )
                == [
                    "FAN SAFETY",
                    "HOLD ACTIVE",
                ],
                "Safety LCD page was incorrect.",
            )

            report(
                "PHASE 3  Safety takes authority"
            )

            writes_after_safety = len(
                executor.decisions
            )

            repeated_safety = service.tick(
                fan_status=fan_status(),
                temperatures_c=(77,),
            )

            require(
                repeated_safety is None,
                "Repeated safety tick emitted a decision.",
            )
            require(
                len(
                    executor.decisions
                )
                == writes_after_safety,
                "Repeated safety tick wrote PWM again.",
            )

            report(
                "PWM      No duplicate safety write"
            )

            for cycle in (
                1,
                2,
            ):
                clock.advance()

                decision = service.tick(
                    fan_status=fan_status(),
                    temperatures_c=(51,),
                )

                require(
                    decision is None,
                    (
                        "Recovery completed before "
                        f"cycle {cycle + 1}."
                    ),
                )

                recovery_status = publish_status(
                    bridge,
                    service,
                )

                require(
                    recovery_status[
                        "recovery_healthy_cycles"
                    ]
                    == cycle,
                    (
                        "Incorrect recovery count "
                        f"at cycle {cycle}."
                    ),
                )
                require(
                    fan_control_page(
                        recovery_status
                    )
                    == [
                        "FAN RECOVERY",
                        f"{cycle} / 3 HEALTHY",
                    ],
                    (
                        "Recovery LCD page was "
                        f"incorrect at cycle {cycle}."
                    ),
                )

                report(
                    (
                        f"PHASE {cycle + 3}  "
                        f"Recovery cycle {cycle} / 3"
                    )
                )

            clock.advance()

            recovery = service.tick(
                fan_status=fan_status(),
                temperatures_c=(51,),
            )

            require(
                recovery is not None,
                "Final recovery produced no decision.",
            )
            require(
                recovery.force_automatic,
                "Final recovery did not force Automatic.",
            )

            record_decision(
                history,
                recovery,
                (51,),
                source=source_for_decision(
                    recovery
                ),
                timestamp=clock(),
            )

            restored = publish_status(
                bridge,
                service,
            )

            require(
                restored[
                    "active_profile"
                ]
                == "automatic",
                "Automatic was not restored.",
            )
            require(
                restored[
                    "control_authority"
                ]
                == "automatic",
                "Automatic authority was not restored.",
            )
            require(
                restored[
                    "safety_hold"
                ]
                is False,
                "Safety hold remained active.",
            )
            require(
                fan_control_page(
                    restored
                )
                == [
                    "FAN CONTROL",
                    "AUTOMATIC",
                ],
                "Restored LCD page was incorrect.",
            )

            report(
                "PHASE 6  Automatic restored"
            )

            events = history.read(
                limit=20
            )
            sources = [
                event.get(
                    "source"
                )
                for event in events
            ]

            require(
                sources.count(
                    "manual"
                )
                == 1,
                "Manual event count was not one.",
            )
            require(
                sources.count(
                    "safety"
                )
                == 1,
                "Safety event count was not one.",
            )
            require(
                sources.count(
                    "recovery"
                )
                == 1,
                "Recovery event count was not one.",
            )

            report(
                "RECORDER Manual command once"
            )
            report(
                "RECORDER Safety escalation once"
            )
            report(
                "RECORDER Safety recovery once"
            )

            require(
                len(
                    executor.decisions
                )
                == 2,
                (
                    "Expected exactly two PWM "
                    "applications: manual "
                    "Afterburners and Automatic "
                    "recovery. Safety authority "
                    "must not duplicate the active "
                    "Afterburners write."
                ),
            )

            report(
                "PWM      Exactly two applications",
                str(
                    len(
                        executor.decisions
                    )
                ),
            )

        finally:
            service.shutdown()

    print()
    print(
        "Fan Control Phase 6: PASS"
    )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(
            main()
        )
    except DrillFailure as error:
        print()
        print(
            f"Fan Control Phase 6: FAIL"
        )
        print(
            f"Reason: {error}"
        )
        raise SystemExit(
            1
        )
