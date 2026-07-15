from types import SimpleNamespace

from truepanel.mission_control.alert_manager import (
    AlertManager,
)
from truepanel.mission_control.constants import Priority


def event(
    event_id="smart.pending",
    message="Pending sectors",
    priority=Priority.WARNING,
    timeout=5,
):
    return SimpleNamespace(
        event_id=event_id,
        message=message,
        priority=priority,
        timeout=timeout,
    )


def test_new_alert_beeps_once():
    manager = AlertManager()
    alert = event()

    assert manager.should_beep(alert) is True
    assert manager.should_beep(alert) is False


def test_same_persistent_alert_stays_silent():
    manager = AlertManager()
    alert = event()

    manager.should_beep(alert)

    for _ in range(10):
        assert manager.should_beep(alert) is False


def test_different_alert_beeps():
    manager = AlertManager()

    first = event(
        event_id="smart.pending",
        message="Pending sectors",
    )
    second = event(
        event_id="pool.degraded",
        message="Pool degraded",
    )

    assert manager.should_beep(first) is True
    assert manager.should_beep(second) is True


def test_changed_message_beeps():
    manager = AlertManager()

    first = event(
        message="160 pending sectors",
    )
    changed = event(
        message="161 pending sectors",
    )

    assert manager.should_beep(first) is True
    assert manager.should_beep(changed) is True


def test_priority_escalation_beeps():
    manager = AlertManager()

    warning = event(
        priority=Priority.WARNING,
    )
    critical = event(
        priority=Priority.CRITICAL,
    )

    assert manager.should_beep(warning) is True
    assert manager.should_beep(critical) is True


def test_same_critical_alert_stays_silent():
    manager = AlertManager()

    critical = event(
        priority=Priority.CRITICAL,
    )

    assert manager.should_beep(critical) is True
    assert manager.should_beep(critical) is False


def test_lower_priority_does_not_beep_again():
    manager = AlertManager()

    critical = event(
        priority=Priority.CRITICAL,
    )
    warning = event(
        priority=Priority.WARNING,
    )

    assert manager.should_beep(critical) is True
    assert manager.should_beep(warning) is False


def test_healthy_event_rearms_alert():
    manager = AlertManager()

    alert = event()
    healthy = event(
        event_id="system.healthy",
        message="All systems healthy",
        priority=Priority.HEALTHY,
    )

    assert manager.should_beep(alert) is True
    assert manager.should_beep(alert) is False

    assert manager.should_beep(healthy) is False

    assert manager.should_beep(alert) is True


def test_evaluate_healthy_event_rearms_alert():
    manager = AlertManager()

    alert = event()
    healthy = event(
        event_id="system.healthy",
        message="All systems healthy",
        priority=Priority.HEALTHY,
    )

    assert manager.should_beep(alert) is True
    assert manager.should_beep(alert) is False

    manager.evaluate(healthy)

    assert manager.should_beep(alert) is True


def test_none_rearms_alert():
    manager = AlertManager()
    alert = event()

    assert manager.should_beep(alert) is True
    assert manager.should_beep(alert) is False

    assert manager.should_beep(None) is False

    assert manager.should_beep(alert) is True


def test_alert_history_behavior_is_preserved():
    manager = AlertManager()
    alert = event()

    assert manager.record(alert) is True
    assert manager.record(alert) is False
    assert manager.get_history() == [alert]
