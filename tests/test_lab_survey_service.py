import pytest

from truepanel.lab.planner import (
    build_plan_from_expression,
)
from truepanel.lab.survey_models import (
    ExecutionState,
)
from truepanel.lab.survey_service import (
    ARMING_PHRASE,
    SurveyService,
)


def safe_plan():
    return build_plan_from_expression(
        "0x00,0x06-0x07",
        allow_experimental_read_only=False,
        allow_experimental_stateful=False,
        allow_documented_writes=False,
    )


def test_service_prepares_simulation():
    service = SurveyService()

    context = service.prepare(
        plan=safe_plan(),
        simulation=True,
        cooldown_seconds=0,
    )

    assert context.authorization.simulation is True
    assert context.plan.count == 3


def test_service_runs_simulation():
    service = SurveyService()

    context = service.prepare(
        plan=safe_plan(),
        simulation=True,
        cooldown_seconds=0,
    )

    service.run(context)

    assert context.state is ExecutionState.COMPLETED
    assert context.healthy is True
    assert context.successes == 3
    assert context.failures == 0
    assert all(
        observation.simulated
        for observation in context.observations
    )


def test_simulation_rejects_controller():
    service = SurveyService()

    context = service.prepare(
        plan=safe_plan(),
        simulation=True,
        cooldown_seconds=0,
    )

    with pytest.raises(
        ValueError,
        match="simulation surveys cannot receive",
    ):
        service.run(
            context,
            controller=object(),
        )


def test_hardware_requires_controller():
    service = SurveyService()

    context = service.prepare(
        plan=safe_plan(),
        simulation=False,
        arming_phrase=ARMING_PHRASE,
        cooldown_seconds=0,
    )

    with pytest.raises(
        ValueError,
        match="hardware surveys require",
    ):
        service.run(context)


def test_hardware_requires_exact_arming_phrase():
    service = SurveyService()

    with pytest.raises(
        PermissionError,
        match="arming phrase",
    ):
        service.prepare(
            plan=safe_plan(),
            simulation=False,
            arming_phrase="almost correct",
            cooldown_seconds=0,
        )
