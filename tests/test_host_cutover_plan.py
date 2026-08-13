from pathlib import Path

from truepanel.host.cutover import (
    build_host_cutover_plan,
    format_host_cutover_plan,
)
from truepanel.host.readiness import (
    HostReadinessCheck,
    HostReadinessReport,
)


def readiness(*, prepared=True):
    checks = (
        HostReadinessCheck(
            "python_activation_locked",
            True,
            "locked",
        ),
        HostReadinessCheck(
            "deployment_safe",
            prepared,
            "safe" if prepared else "review",
        ),
    )

    return HostReadinessReport(
        root="/",
        checks=checks,
    )


def test_cutover_plan_is_explicitly_non_executable():
    plan = build_host_cutover_plan(
        readiness()
    )

    assert plan.prepared_safely is True
    assert plan.activation_state == "locked"
    assert plan.execution_enabled is False

    payload = plan.to_dict()
    assert payload["schema_version"] == 1
    assert payload["execution_enabled"] is False


def test_forward_plan_releases_embedded_owner_before_marker_and_start():
    plan = build_host_cutover_plan(
        readiness()
    )
    actions = [
        step.action
        for step in plan.cutover_steps
    ]

    stop_embedded = next(
        index
        for index, action in enumerate(actions)
        if "Stop the legacy LCD service" in action
    )
    marker = next(
        index
        for index, action in enumerate(actions)
        if "Create the ephemeral" in action
    )
    start_standalone = next(
        index
        for index, action in enumerate(actions)
        if "Start the standalone Host Agent" in action
    )
    start_lcd = next(
        index
        for index, action in enumerate(actions)
        if "Start the LCD service" in action
    )

    assert stop_embedded < marker < start_standalone < start_lcd


def test_rollback_releases_standalone_owner_before_marker_removal():
    plan = build_host_cutover_plan(
        readiness()
    )
    actions = [
        step.action
        for step in plan.rollback_steps
    ]

    stop_standalone = next(
        index
        for index, action in enumerate(actions)
        if "Stop the standalone Host Agent" in action
    )
    remove_marker = next(
        index
        for index, action in enumerate(actions)
        if "Remove the ephemeral" in action
    )
    start_lcd = next(
        index
        for index, action in enumerate(actions)
        if "Start the LCD service" in action
    )

    assert stop_standalone < remove_marker < start_lcd


def test_unprepared_readiness_is_visible_but_plan_remains_available():
    plan = build_host_cutover_plan(
        readiness(prepared=False)
    )

    assert plan.prepared_safely is False
    assert len(plan.cutover_steps) == 6
    assert len(plan.rollback_steps) == 4
    assert plan.execution_enabled is False


def test_cutover_plan_formatter_emphasizes_disabled_execution():
    text = format_host_cutover_plan(
        build_host_cutover_plan(readiness())
    )

    assert "Cutover execution: DISABLED" in text
    assert "Forward cutover:" in text
    assert "Rollback:" in text


def test_cutover_planner_is_strictly_passive():
    source = Path(
        "truepanel/host/cutover.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "subprocess",
        "systemctl",
        ".write_text(",
        ".touch(",
        ".mkdir(",
        ".unlink(",
        "os.remove(",
        "HostOwnershipGuard",
        "flock",
    ):
        assert forbidden not in source
