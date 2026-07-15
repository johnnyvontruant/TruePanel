"""
Project Stargate Display Experiment Runner.

Executes display experiments using documented LCD operations.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from truepanel.lab.display_experiment import (
    DisplayExperiment,
    DisplayFrame,
)


@dataclass(frozen=True)
class FrameExecution:
    """One executed frame."""

    index: int
    total: int
    frame: DisplayFrame


class DisplayExperimentRunner:
    """
    Executes DisplayExperiment instances.

    The runner performs only documented LCD operations:
      * clear()
      * write_frame()

    It has no knowledge of serial protocol details.
    """

    def __init__(
        self,
        controller,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._controller = controller
        self._sleep = sleep

    def run(
        self,
        experiment: DisplayExperiment,
        *,
        callback: Callable[[FrameExecution], None] | None = None,
    ) -> None:
        """
        Execute every frame in the experiment.
        """

        self._controller.clear()

        total = len(experiment.frames)

        for index, frame in enumerate(
            experiment.frames,
            start=1,
        ):
            self._controller.write_frame(
                frame.line1,
                frame.line2,
            )

            if callback is not None:
                callback(
                    FrameExecution(
                        index=index,
                        total=total,
                        frame=frame,
                    )
                )

            self._sleep(frame.duration_seconds)

        self._controller.clear()
