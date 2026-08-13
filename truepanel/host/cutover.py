"""Passive standalone Host Agent cutover planning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .readiness import HostReadinessReport


@dataclass(frozen=True)
class HostCutoverStep:
    """One ordered operator action in a future Host ownership handoff."""

    sequence: int
    action: str
    safety_purpose: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "action": self.action,
            "safety_purpose": self.safety_purpose,
        }


@dataclass(frozen=True)
class HostCutoverPlan:
    """A descriptive, non-executable Host ownership cutover plan."""

    prepared_safely: bool
    activation_state: str
    execution_enabled: bool
    cutover_steps: tuple[HostCutoverStep, ...]
    rollback_steps: tuple[HostCutoverStep, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "prepared_safely": self.prepared_safely,
            "activation_state": self.activation_state,
            "execution_enabled": self.execution_enabled,
            "cutover_steps": [
                step.to_dict()
                for step in self.cutover_steps
            ],
            "rollback_steps": [
                step.to_dict()
                for step in self.rollback_steps
            ],
        }


def _steps(
    entries: tuple[tuple[str, str], ...],
) -> tuple[HostCutoverStep, ...]:
    return tuple(
        HostCutoverStep(
            sequence=index,
            action=action,
            safety_purpose=safety_purpose,
        )
        for index, (action, safety_purpose) in enumerate(
            entries,
            start=1,
        )
    )


def build_host_cutover_plan(
    readiness: HostReadinessReport,
) -> HostCutoverPlan:
    """Build the future ownership handoff plan without mutating host state."""

    cutover_steps = _steps(
        (
            (
                "Deploy a release that explicitly unlocks standalone Host Agent activation.",
                "Activation authority changes only through an intentional software release.",
            ),
            (
                "Stop the legacy LCD service and wait for embedded Host shutdown to complete.",
                "The embedded owner restores Automatic control and releases the Host ownership lease before another owner may start.",
            ),
            (
                "Create the ephemeral standalone Host Agent cutover marker.",
                "The marker selects external Host mode for the next LCD process and satisfies the dormant systemd condition.",
            ),
            (
                "Start the standalone Host Agent service.",
                "The standalone process must acquire the single-owner lease before exposing privileged command handling.",
            ),
            (
                "Verify standalone Host heartbeat, fan status, and ownership health.",
                "The new privileged owner is proven healthy before the LCD application returns.",
            ),
            (
                "Start the LCD service and verify that it resolves external Host mode.",
                "The LCD returns as a UI-only consumer and must not construct an embedded Host runtime.",
            ),
        )
    )

    rollback_steps = _steps(
        (
            (
                "Stop the LCD service if it is running in external Host mode.",
                "Application restart cannot race the ownership rollback.",
            ),
            (
                "Stop the standalone Host Agent and wait for Automatic restoration and ownership release.",
                "No embedded owner may start while the standalone owner still holds hardware authority.",
            ),
            (
                "Remove the ephemeral standalone Host Agent cutover marker.",
                "The next LCD start resolves embedded Host mode again.",
            ),
            (
                "Start the LCD service and verify embedded Host ownership health.",
                "The legacy owner is restored only after the standalone lease has been released.",
            ),
        )
    )

    return HostCutoverPlan(
        prepared_safely=readiness.prepared_safely,
        activation_state=readiness.activation_state,
        execution_enabled=False,
        cutover_steps=cutover_steps,
        rollback_steps=rollback_steps,
    )


def format_host_cutover_plan(
    plan: HostCutoverPlan,
) -> str:
    """Format the non-executable handoff plan for operators."""

    lines = [
        "TruePanel Host Agent Cutover Plan",
        "=================================",
        "",
        (
            "Dormant deployment prepared safely: "
            + ("YES" if plan.prepared_safely else "NO")
        ),
        f"Standalone activation: {plan.activation_state.upper()}",
        "Cutover execution: DISABLED",
        "",
        "Forward cutover:",
    ]

    for step in plan.cutover_steps:
        lines.append(
            f"  {step.sequence}. {step.action}"
        )
        lines.append(
            f"     Safety: {step.safety_purpose}"
        )

    lines.extend(
        [
            "",
            "Rollback:",
        ]
    )

    for step in plan.rollback_steps:
        lines.append(
            f"  {step.sequence}. {step.action}"
        )
        lines.append(
            f"     Safety: {step.safety_purpose}"
        )

    return "\n".join(lines)


__all__ = [
    "HostCutoverPlan",
    "HostCutoverStep",
    "build_host_cutover_plan",
    "format_host_cutover_plan",
]
