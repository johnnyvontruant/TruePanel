"""
Stateful ZFS storage-operation watcher.

Tracks scrub and resilver lifecycles, emits progress events while operations
are active, and emits one-shot completion events when they finish.

The exported ``zfs_watcher`` remains a callable singleton, preserving existing
Mission Control registration.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..constants import Category, Priority
from ..event import MissionEvent


def _integer(value: Any) -> int | None:
    if value is None:
        return None

    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None


class ZFSOperationWatcher:
    """
    Track scrub and resilver operation transitions.

    Supported lifecycle events:

    * operation started;
    * operation progress;
    * operation completed; and
    * operation problem.
    """

    def __init__(self):
        self.active_operation: str | None = None
        self.last_percent: int | None = None
        self.last_problem = False

    def reset(self):
        self.active_operation = None
        self.last_percent = None
        self.last_problem = False

    @staticmethod
    def _operation(activity: Mapping[str, Any]) -> str | None:
        # A resilver is more urgent and takes precedence if malformed state
        # reports both operations simultaneously.
        if activity.get("resilver_running"):
            return "resilver"

        if activity.get("scrub_running"):
            return "scrub"

        return None

    @staticmethod
    def _event(
        operation: str,
        phase: str,
        *,
        percent: int | None,
        remaining: str | None,
        problem: bool,
        previous_percent: int | None = None,
    ) -> MissionEvent:
        operation_title = operation.upper()
        event_id = f"storage.{operation}"

        if problem:
            priority = Priority.WARNING
            title = f"{operation_title} ALERT"
            message = remaining or "Operation problem"
            timeout = 10
            event_id = f"{event_id}.problem"

        elif phase == "completed":
            priority = Priority.HEALTHY
            title = f"{operation_title} DONE"
            message = "Pool operation complete"
            timeout = 7
            event_id = f"{event_id}.completed"

        else:
            priority = Priority.INFO
            title = operation_title
            message = f"{percent}%" if percent is not None else "Running"
            timeout = 10

        return MissionEvent(
            priority=priority,
            title=title,
            message=message,
            category=Category.STORAGE,
            timeout=timeout,
            event_id=event_id,
            source="zfs_watcher",
            metadata={
                "change_type": (
                    "operation_problem"
                    if problem
                    else f"operation_{phase}"
                ),
                "operation": operation,
                "phase": phase,
                "percent": percent,
                "previous_percent": previous_percent,
                "remaining": remaining,
                "problem": problem,
            },
        )

    def __call__(self, state):
        activity = state.get("zfs_activity", {})

        if not isinstance(activity, Mapping) or not activity:
            return None

        operation = self._operation(activity)
        percent = _integer(activity.get("percent"))
        remaining = _text(activity.get("remaining"))
        problem = bool(activity.get("problem"))

        if operation is None:
            if self.active_operation is None:
                self.last_problem = problem
                return None

            completed_operation = self.active_operation
            previous_percent = self.last_percent

            self.reset()

            return self._event(
                completed_operation,
                "completed",
                percent=100,
                previous_percent=previous_percent,
                remaining=remaining,
                problem=False,
            )

        operation_changed = operation != self.active_operation

        if operation_changed:
            previous_percent = self.last_percent
            self.active_operation = operation
            self.last_percent = percent
            self.last_problem = problem

            return self._event(
                operation,
                "started",
                percent=percent,
                previous_percent=previous_percent,
                remaining=remaining,
                problem=problem,
            )

        problem_changed = problem != self.last_problem
        percent_changed = percent != self.last_percent

        previous_percent = self.last_percent
        self.last_percent = percent
        self.last_problem = problem

        if problem_changed or percent_changed:
            return self._event(
                operation,
                "progress",
                percent=percent,
                previous_percent=previous_percent,
                remaining=remaining,
                problem=problem,
            )

        # Continue returning the active operation so it remains available to
        # Mission Control even when the percentage has not advanced.
        return self._event(
            operation,
            "progress",
            percent=percent,
            previous_percent=previous_percent,
            remaining=remaining,
            problem=problem,
        )


zfs_watcher = ZFSOperationWatcher()


__all__ = [
    "ZFSOperationWatcher",
    "zfs_watcher",
]
