from dataclasses import dataclass

from truepanel.lab.display_patterns import (
    DisplayPattern,
    patterns,
)


@dataclass(frozen=True)
class DisplayStep:
    action: str
    line1: str = ""
    line2: str = ""
    delay_seconds: float = 1.0


def build_display_characterization(
    delay_seconds: float = 1.0,
) -> list[DisplayStep]:
    """
    Build the standard display characterization sequence.
    """

    sequence = [
        DisplayStep(
            action="clear",
            delay_seconds=delay_seconds,
        )
    ]

    for display in patterns():
        sequence.append(
            DisplayStep(
                action="write",
                line1=display.line1,
                line2=display.line2,
                delay_seconds=delay_seconds,
            )
        )

    sequence.append(
        DisplayStep(
            action="clear",
            delay_seconds=delay_seconds,
        )
    )

    return sequence
