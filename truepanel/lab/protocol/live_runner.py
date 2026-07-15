"""
Bounded live runner for approved protocol experiments.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from .archive import ProtocolArchive
from .authorization import ProtocolAuthorization
from .experiment import ProtocolExperiment
from .observation import (
    ObservationOutcome,
    ProtocolObservation,
)
from .restore import ProtocolRestorer
from .run import (
    ProtocolRun,
    RunState,
    StepExecution,
)
from .sequence import StepOperation
from .validator import ProtocolExperimentValidator


class ProtocolLiveRunner:
    """
    Execute only validated and authorized protocol sequences.

    The controller must provide send(bytes). Restoration is attempted in a
    finally block whether execution succeeds, fails, or is interrupted.
    """

    def __init__(
        self,
        controller,
        *,
        validator=None,
        archive=None,
        sleep=time.sleep,
        clock=time.monotonic,
        now=lambda: datetime.now(UTC),
    ):
        send = getattr(
            controller,
            "send",
            None,
        )

        if not callable(send):
            raise TypeError(
                "controller must provide send(bytes)"
            )

        self.controller = controller
        self.validator = (
            validator
            or ProtocolExperimentValidator()
        )
        self.archive = archive
        self.sleep = sleep
        self.clock = clock
        self.now = now
        self.restorer = ProtocolRestorer(
            send
        )

    def run(
        self,
        experiment,
        authorization,
        *,
        callback=None,
        observer=None,
        controller_family="A125",
    ):
        if not isinstance(
            experiment,
            ProtocolExperiment,
        ):
            raise TypeError(
                "experiment must be a ProtocolExperiment"
            )

        if not isinstance(
            authorization,
            ProtocolAuthorization,
        ):
            raise TypeError(
                "authorization must be ProtocolAuthorization"
            )

        validation = self.validator.validate(
            experiment,
            controller_family=controller_family,
        )

        if not validation.valid:
            raise PermissionError(
                validation.message
            )

        authorization.consume(
            experiment.experiment_id,
            clock=self.clock,
        )

        started_at = self.now()
        executions = []
        observations = []
        state = RunState.RUNNING
        error_text = ""
        restore_packet = None
        restored = False

        try:
            total = len(experiment.sequence)

            for index, step in enumerate(
                experiment.sequence,
                start=1,
            ):
                if step.operation is StepOperation.RESTORE:
                    restore_packet = step.payload
                    continue

                step_started = self.clock()

                if step.operation is StepOperation.TRANSMIT:
                    self.controller.send(
                        step.payload
                    )

                elif step.operation is StepOperation.DELAY:
                    self.sleep(
                        step.delay_seconds
                    )

                elif (
                    step.operation
                    is StepOperation.DISPLAY_VERIFY
                ):
                    pass

                duration_ms = max(
                    0.0,
                    (
                        self.clock()
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

                executions.append(
                    execution
                )

                if callback is not None:
                    callback(execution)

            if observer is None:
                observations.append(
                    ProtocolObservation(
                        experiment_id=(
                            experiment.experiment_id
                        ),
                        outcome=(
                            ObservationOutcome.INCONCLUSIVE
                        ),
                        visible_effect=(
                            "Live sequence completed; "
                            "no observer result supplied"
                        ),
                        restored=False,
                        metadata={
                            "simulation": False,
                            "validation": (
                                validation.as_dict()
                            ),
                        },
                    )
                )
            else:
                observed = observer(
                    experiment
                )

                if isinstance(
                    observed,
                    ProtocolObservation,
                ):
                    observations.append(
                        observed
                    )
                else:
                    raise TypeError(
                        "observer must return ProtocolObservation"
                    )

            state = RunState.COMPLETED

        except KeyboardInterrupt:
            state = RunState.ABORTED
            error_text = (
                "Experiment interrupted by operator"
            )

        except Exception as error:
            state = RunState.FAILED
            error_text = str(error)

        finally:
            restore_result = self.restorer.restore(
                restore_packet
            )
            restored = restore_result.succeeded

        observations = tuple(
            ProtocolObservation(
                experiment_id=item.experiment_id,
                outcome=item.outcome,
                visible_effect=item.visible_effect,
                response_bytes=item.response_bytes,
                duration_ms=item.duration_ms,
                repeat_index=item.repeat_index,
                restored=restored,
                notes=item.notes,
                metadata={
                    **item.metadata,
                    "restore": restore_result.as_dict(),
                },
                timestamp=item.timestamp,
            )
            for item in observations
        )

        run = ProtocolRun(
            experiment=experiment,
            state=state,
            steps=tuple(executions),
            observations=observations,
            started_at=started_at,
            completed_at=self.now(),
            simulation=False,
            error=error_text,
        )

        if self.archive is not None:
            self.archive.save_experiment(
                experiment
            )
            self.archive.save_run(run)

        return run
