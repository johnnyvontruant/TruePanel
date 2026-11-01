"""
Project Stargate Display Experiment Model.

Defines repeatable display experiments without executing them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from truepanel.lab.display_patterns import (
    DisplayPattern,
    patterns,
)


@dataclass(frozen=True)
class DisplayFrame:
    """One LCD frame."""

    line1: str
    line2: str
    duration_seconds: float = 1.0


@dataclass
class DisplayExperiment:
    """A sequence of LCD frames."""

    name: str
    frames: list[DisplayFrame] = field(
        default_factory=list
    )

    def add(
        self,
        pattern: DisplayPattern,
        *,
        duration_seconds: float = 1.0,
    ) -> None:
        self.frames.append(
            DisplayFrame(
                line1=pattern.line1,
                line2=pattern.line2,
                duration_seconds=duration_seconds,
            )
        )


def build_characterization(
    *,
    duration_seconds: float = 1.0,
) -> DisplayExperiment:
    """
    Build the standard display characterization experiment.
    """

    experiment = DisplayExperiment(
        name="display-characterization"
    )

    for item in patterns():
        experiment.add(
            item,
            duration_seconds=duration_seconds,
        )

    return experiment
