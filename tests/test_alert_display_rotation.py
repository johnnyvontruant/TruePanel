from pathlib import Path

from truepanel.mission_control.alert_manager import (
    AlertManager,
    AlertState,
)
from truepanel.mission_control.constants import (
    Category,
    Priority,
)
from truepanel.mission_control.display_manager import (
    DisplayManager,
    DisplayMode,
)
from truepanel.mission_control.event import MissionEvent


def make_event(
    event_id="smart.pending",
    message="sda 1",
    priority=Priority.CRITICAL,
):
    return MissionEvent(
        priority=priority,
        title="PENDING SECT",
        message=message,
        category=Category.STORAGE,
        timeout=15,
        event_id=event_id,
        source="smart_watcher",
    )


def test_unchanged_alert_interrupts_only_once():
    manager = AlertManager()
    alert = make_event()

    first = manager.evaluate(alert)
    repeated = manager.evaluate(alert)

    assert first.interrupt is True
    assert first.state is AlertState.NEW
    assert repeated.interrupt is False
    assert repeated.state is AlertState.ACTIVE


def test_changed_message_interrupts_again():
    manager = AlertManager()

    manager.evaluate(
        make_event(message="sda 1")
    )

    changed = manager.evaluate(
        make_event(message="sda 2")
    )

    assert changed.interrupt is True


def test_different_alert_interrupts_again():
    manager = AlertManager()
    manager.evaluate(make_event())

    different = manager.evaluate(
        make_event(
            event_id="pool.degraded",
            message="tank DEGRADED",
        )
    )

    assert different.interrupt is True


def test_priority_escalation_interrupts_again():
    manager = AlertManager()

    manager.evaluate(
        make_event(
            priority=Priority.WARNING,
        )
    )

    escalated = manager.evaluate(
        make_event(
            priority=Priority.CRITICAL,
        )
    )

    assert escalated.interrupt is True


def test_lower_priority_does_not_repeat():
    manager = AlertManager()

    manager.evaluate(
        make_event(
            priority=Priority.CRITICAL,
        )
    )

    lowered = manager.evaluate(
        make_event(
            priority=Priority.WARNING,
        )
    )

    assert lowered.interrupt is False
    assert lowered.state is AlertState.ACTIVE


def test_recovery_rearms_interrupt():
    manager = AlertManager()
    alert = make_event()

    manager.evaluate(alert)
    assert manager.evaluate(alert).interrupt is False

    healthy = MissionEvent(
        priority=Priority.HEALTHY,
        title="MISSION READY",
        message="All systems healthy",
        category=Category.SYSTEM,
        timeout=5,
        event_id="system.healthy",
    )

    for _ in range(manager.recovery_observations):
        manager.evaluate(healthy)

    assert manager.evaluate(alert).interrupt is True


class FixedMission:
    def __init__(self, event):
        self.event = event

    def evaluate(self, state):
        return self.event


class EmptyRegistry:
    dashboard_pages = []


def test_persistent_smart_alert_remains_in_dashboard():
    alert = make_event()
    manager = AlertManager()

    display = DisplayManager(
        FixedMission(alert),
        manager,
        registry=EmptyRegistry(),
    )

    first = display.evaluate({})
    repeated = display.evaluate({})

    assert first.interrupt is True
    assert repeated.interrupt is False

    dashboard = display._dashboard_smart(
        {
            "smart": [
                {
                    "drive": "sda",
                    "health": "PASSED",
                    "pending": 1,
                    "offline_uncorrectable": 0,
                    "media_errors": 0,
                    "critical_warning": "0x00",
                }
            ]
        }
    )

    assert dashboard.mode == DisplayMode.DASHBOARD
    assert dashboard.interrupt is False
    assert "SMART ALERT" in " ".join(
        dashboard.lines
    )


def test_lcd_loop_resumes_after_interrupt():
    source = Path("lcd-menu.py").read_text(
        encoding="utf-8",
    )

    expected = (
        "            maybe_show_alert()\n"
        "            menu[menu_item]()"
    )

    assert expected in source


def test_alert_check_cannot_skip_menu_advancement():
    source = Path("lcd-menu.py").read_text(
        encoding="utf-8",
    )

    loop_start = source.index(
        "        while not shutdown_requested:"
    )

    loop_end = source.index(
        "    finally:",
        loop_start,
    )

    loop_source = source[loop_start:loop_end]

    assert "if maybe_show_alert():" not in loop_source
    assert "maybe_show_alert()" in loop_source
    assert "menu_item + 1" in loop_source

    assert (
        "detail = "
        "display_manager.render_alert_detail"
        not in source
    )

def test_transient_healthy_sample_does_not_rearm_alert():
    manager = AlertManager()
    alert = make_event()

    healthy = MissionEvent(
        priority=Priority.HEALTHY,
        title="MISSION READY",
        message="All systems healthy",
        category=Category.SYSTEM,
        timeout=5,
        event_id="system.healthy",
    )

    assert manager.evaluate(alert).interrupt is True
    assert manager.evaluate(healthy).interrupt is False
    assert manager.evaluate(alert).interrupt is False


def test_three_healthy_samples_rearm_alert():
    manager = AlertManager()
    alert = make_event()

    healthy = MissionEvent(
        priority=Priority.HEALTHY,
        title="MISSION READY",
        message="All systems healthy",
        category=Category.SYSTEM,
        timeout=5,
        event_id="system.healthy",
    )

    assert manager.evaluate(alert).interrupt is True

    for _ in range(3):
        manager.evaluate(healthy)

    assert manager.evaluate(alert).interrupt is True


def test_alternating_alerts_do_not_retrigger_each_other():
    manager = AlertManager()

    pending = make_event(
        event_id="smart.pending",
        message="sda 1",
        priority=Priority.CRITICAL,
    )

    thermal = make_event(
        event_id="thermal.hot",
        message="CPU 91C",
        priority=Priority.WARNING,
    )

    assert manager.evaluate(pending).interrupt is True
    assert manager.evaluate(thermal).interrupt is True
    assert manager.evaluate(pending).interrupt is False
    assert manager.evaluate(thermal).interrupt is False

def test_event_queue_does_not_capture_both_navigation_buttons():
    source = Path("lcd-menu.py").read_text(
        encoding="utf-8",
    )

    assert (
        "if menu[menu_item] == show_event_queue:"
        not in source
    )


def test_alert_history_does_not_capture_both_navigation_buttons():
    source = Path("lcd-menu.py").read_text(
        encoding="utf-8",
    )

    assert (
        "if menu[menu_item] == show_alert_history:"
        not in source
    )


def test_left_and_right_buttons_move_main_menu():
    source = Path("lcd-menu.py").read_text(
        encoding="utf-8",
    )

    assert (
        "menu_item = (menu_item - 1) % len(menu)"
        in source
    )

    assert (
        "menu_item = (menu_item + 1) % len(menu)"
        in source
    )

def test_primary_menu_excludes_alert_diagnostic_pages():
    source = Path("lcd-menu.py").read_text(
        encoding="utf-8",
    )

    start = source.index("menu = [")
    end = source.index(
        "]",
        start,
    )

    menu_source = source[start:end]

    assert "show_mission_control," not in menu_source
    assert "show_event_queue," not in menu_source
    assert "show_alert_history," not in menu_source


def test_interrupt_timeout_is_followed_by_normal_page_render():
    source = Path("lcd-menu.py").read_text(
        encoding="utf-8",
    )

    expected = (
        "            maybe_show_alert()\n"
        "            menu[menu_item]()"
    )

    assert expected in source


def test_primary_pages_rotate_every_five_seconds():
    source = Path("lcd-menu.py").read_text(
        encoding="utf-8",
    )

    assert "            delay = 5" in source


def test_backlight_timeout_covers_complete_rotation():
    source = Path("lcd-menu.py").read_text(
        encoding="utf-8",
    )

    assert "DISPLAY_TIMEOUT = 120" in source
