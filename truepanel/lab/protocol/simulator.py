"""
Simulation-only protocol experiment runner.

This runner never opens serial ports and never invokes hardware methods.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Callable

from .experiment import ProtocolExperiment
from .observation import (
    ObservationOutcome,
    ProtocolObservation,
)
from .run import (
    ProtocolRun,
    RunState,
    StepExecution,
)
from .sequence import StepOperation


class ProtocolSimulationRunner:
    """
    Deterministically walk a protocol experiment without hardware access.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = (
            lambda: datetime.now(UTC)
        ),
        sleep: Callable[[float], None] | None = None,
    ):
        self._clock = clock
        self._now = now
        self._sleep = sleep or (
            lambda _seconds: None
        )

    def run(
        self,
        experiment,
        *,
        callback=None,
    ):
        if not isinstance(
            experiment,
            ProtocolExperiment,
        ):
            raise TypeError(
                "experiment must be a ProtocolExperiment"
            )

        started_at = self._now()
        executions = []

        try:
            total = len(experiment.sequence)

            for index, step in enumerate(
                experiment.sequence,
                start=1,
            ):
                step_started = self._clock()

                if step.operation is StepOperation.DELAY:
                    self._sleep(
                        step.delay_seconds
                    )

                duration_ms = max(
                    0.0,
                    (
                        self._clock()
                        - step_started
                    )
                    * 1000.0,
                )

                execution = StepExecution(
                    index=index,
                    total=total,
                    operation=step.operation.value,
                    description=step.description,
                    payload=step.payload,
                    duration_ms=duration_ms,
                )

                executions.append(execution)

                if callback is not None:
                    callback(execution)

            observations = tuple(
                ProtocolObservation(
                    experiment_id=(
                        experiment.experiment_id
                    ),
                    outcome=(
                        ObservationOutcome.INCONCLUSIVE
                    ),
                    visible_effect=(
                        "Simulation completed; "
                        "no hardware observation available"
                    ),
                    repeat_index=index,
                    restored=(
                        experiment.sequence.has_restore
                    ),
                    notes=(
                        "Simulation-only protocol run"
                    ),
                    metadata={
                        "simulation": True,
                        "risk": experiment.risk.value,
                    },
                )
                for index in range(
                    1,
                    experiment.repeat_count + 1,
                )
            )

            return ProtocolRun(
                experiment=experiment,
                state=RunState.COMPLETED,
                steps=tuple(executions),
                observations=observations,
                started_at=started_at,
                completed_at=self._now(),
                simulation=True,
            )

        except Exception as error:
            return ProtocolRun(
                experiment=experiment,
                state=RunState.FAILED,
                steps=tuple(executions),
                observations=(),
                started_at=started_at,
                completed_at=self._now(),
                simulation=True,
                error=str(error),
            )
