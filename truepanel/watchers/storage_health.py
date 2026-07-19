"""
Stateful storage-health watcher for Mission Control.

The watcher periodically collects a hardware health report, compares it with
the previous snapshot, converts meaningful changes into MissionEvent objects,
and optionally records emitted events as newline-delimited JSON.

Mission Control watchers are callables accepting the current application state
and returning either one MissionEvent or None.
"""

from __future__ import annotations

import logging

import json
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from truepanel.hardware.health_commands import build_health_report
from truepanel.hardware.manager import HardwareManager
from truepanel.mission_control.constants import Category, Priority
from truepanel.mission_control.event import MissionEvent


HealthReport = Mapping[str, Any]
ReportProvider = Callable[[], HealthReport]
Clock = Callable[[], float]


_STATE_PRIORITY = {
    "healthy": Priority.HEALTHY,
    "unknown": Priority.INFO,
    "warning": Priority.WARNING,
    "critical": Priority.CRITICAL,
}

_STATE_RANK = {
    "healthy": 0,
    "unknown": 1,
    "warning": 2,
    "critical": 3,
}

_COUNTER_FIELDS = (
    "reallocated_sectors",
    "pending_sectors",
    "offline_uncorrectable",
    "interface_errors",
)


def _integer(value: Any) -> int | None:
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _device_key(device: Mapping[str, Any]) -> str:
    """
    Return the most stable available identity for one storage device.

    Serial numbers survive Linux device-name changes. When a serial is absent,
    the device name remains a useful fallback.
    """

    serial = str(device.get("serial") or "").strip()

    if serial:
        return f"serial:{serial}"

    name = str(device.get("device") or "").strip()

    if name:
        return f"device:{name}"

    path = str(device.get("device_path") or "").strip()

    if path:
        return f"path:{path}"

    return f"unknown:{id(device)}"


def _label(device: Mapping[str, Any]) -> str:
    return str(
        device.get("label")
        or device.get("device_path")
        or device.get("device")
        or "Storage"
    )


def _telemetry(device: Mapping[str, Any]) -> Mapping[str, Any]:
    value = device.get("telemetry", {})
    return value if isinstance(value, Mapping) else {}


def _snapshot_device(device: Mapping[str, Any]) -> dict[str, Any]:
    """
    Normalize the health fields used for change detection and recording.
    """

    telemetry = _telemetry(device)

    return {
        "key": _device_key(device),
        "device": device.get("device"),
        "device_path": device.get("device_path"),
        "label": _label(device),
        "serial": device.get("serial"),
        "model": device.get("model"),
        "category": device.get("category"),
        "physical_bay": device.get("physical_bay"),
        "state": str(device.get("state") or "unknown").lower(),
        "message": str(device.get("message") or ""),
        "temperature_c": _integer(
            device.get("temperature_c", telemetry.get("temperature_c"))
        ),
        "smart_passed": device.get(
            "smart_passed",
            telemetry.get("smart_passed"),
        ),
        "reallocated_sectors": _integer(
            telemetry.get("reallocated_sectors")
        ),
        "pending_sectors": _integer(
            telemetry.get("pending_sectors")
        ),
        "offline_uncorrectable": _integer(
            telemetry.get("offline_uncorrectable")
        ),
        "interface_errors": _integer(
            telemetry.get("interface_errors")
        ),
        "percentage_used": _integer(
            telemetry.get("percentage_used")
        ),
        "available_spare": _integer(
            telemetry.get("available_spare")
        ),
        "source": device.get("source") or telemetry.get("source"),
        "collected_at": telemetry.get("collected_at"),
    }


@dataclass(frozen=True)
class StorageHealthChange:
    """
    One meaningful change between storage-health snapshots.
    """

    change_type: str
    device_key: str
    label: str
    old_state: str | None
    new_state: str | None
    message: str
    priority: Priority
    old: dict[str, Any] | None
    new: dict[str, Any] | None

    def to_event(self) -> MissionEvent:
        identity = (
            self.new
            or self.old
            or {}
        )

        device = str(
            identity.get("device")
            or identity.get("serial")
            or self.device_key
        ).replace("/", "_")

        title = self.label

        if self.change_type == "device_missing":
            title = "Drive Missing"
        elif self.change_type == "device_inserted":
            title = "Drive Detected"
        elif self.change_type == "media_counter_increased":
            title = "Media Errors"
        elif self.change_type == "temperature_increased":
            title = "Drive Temperature"
        elif self.change_type == "recovered":
            title = "Drive Recovered"
        elif self.new_state == "critical":
            title = "Drive Critical"

        metadata = {
            "change_type": self.change_type,
            "device_key": self.device_key,
            "device": identity.get("device"),
            "device_path": identity.get("device_path"),
            "label": self.label,
            "serial": identity.get("serial"),
            "model": identity.get("model"),
            "category": identity.get("category"),
            "physical_bay": identity.get("physical_bay"),
            "old_state": self.old_state,
            "new_state": self.new_state,
            "temperature_c": identity.get("temperature_c"),
            "smart_passed": identity.get("smart_passed"),
            "reallocated_sectors": identity.get(
                "reallocated_sectors"
            ),
            "pending_sectors": identity.get("pending_sectors"),
            "offline_uncorrectable": identity.get(
                "offline_uncorrectable"
            ),
            "interface_errors": identity.get("interface_errors"),
            "percentage_used": identity.get("percentage_used"),
            "available_spare": identity.get("available_spare"),
            "health_message": self.message,
        }

        return MissionEvent(
            priority=self.priority,
            title=title,
            message=self.message,
            category=Category.STORAGE,
            timeout=10 if self.priority >= Priority.CRITICAL else 7,
            event_id=f"storage.{device}.{self.change_type}",
            source="storage_health_watcher",
            metadata=metadata,
        )


class StorageHealthDiffer:
    """
    Compare normalized storage-health snapshots.
    """

    def snapshot(
        self,
        report: HealthReport,
    ) -> dict[str, dict[str, Any]]:
        devices = report.get("devices", [])

        if not isinstance(devices, list):
            return {}

        normalized = (
            _snapshot_device(device)
            for device in devices
            if isinstance(device, Mapping)
        )

        return {
            device["key"]: device
            for device in normalized
        }

    def initial_changes(
        self,
        current: Mapping[str, dict[str, Any]],
    ) -> list[StorageHealthChange]:
        """
        Report existing warning and critical conditions at startup.

        Healthy and unknown devices establish baseline silently.
        """

        changes = []

        for key, device in current.items():
            state = device["state"]

            if state not in {"warning", "critical"}:
                continue

            changes.append(
                StorageHealthChange(
                    change_type="initial_condition",
                    device_key=key,
                    label=device["label"],
                    old_state=None,
                    new_state=state,
                    message=device["message"] or state,
                    priority=_STATE_PRIORITY.get(
                        state,
                        Priority.INFO,
                    ),
                    old=None,
                    new=device,
                )
            )

        return self._ordered(changes)

    def compare(
        self,
        previous: Mapping[str, dict[str, Any]],
        current: Mapping[str, dict[str, Any]],
    ) -> list[StorageHealthChange]:
        changes: list[StorageHealthChange] = []

        previous_keys = set(previous)
        current_keys = set(current)

        for key in sorted(previous_keys - current_keys):
            old = previous[key]

            changes.append(
                StorageHealthChange(
                    change_type="device_missing",
                    device_key=key,
                    label=old["label"],
                    old_state=old["state"],
                    new_state=None,
                    message=f"{old['label']} disappeared",
                    priority=Priority.CRITICAL,
                    old=old,
                    new=None,
                )
            )

        for key in sorted(current_keys - previous_keys):
            new = current[key]
            state = new["state"]

            changes.append(
                StorageHealthChange(
                    change_type="device_inserted",
                    device_key=key,
                    label=new["label"],
                    old_state=None,
                    new_state=state,
                    message=f"{new['label']} detected",
                    priority=(
                        _STATE_PRIORITY.get(state, Priority.INFO)
                        if state in {"warning", "critical"}
                        else Priority.INFO
                    ),
                    old=None,
                    new=new,
                )
            )

        for key in sorted(previous_keys & current_keys):
            old = previous[key]
            new = current[key]

            state_change = self._state_change(key, old, new)

            if state_change is not None:
                changes.append(state_change)

            counter_change = self._counter_change(key, old, new)

            if counter_change is not None:
                changes.append(counter_change)

            temperature_change = self._temperature_change(
                key,
                old,
                new,
            )

            if temperature_change is not None:
                changes.append(temperature_change)

        return self._ordered(changes)

    def _state_change(
        self,
        key: str,
        old: dict[str, Any],
        new: dict[str, Any],
    ) -> StorageHealthChange | None:
        old_state = old["state"]
        new_state = new["state"]

        if old_state == new_state:
            return None

        old_rank = _STATE_RANK.get(old_state, 1)
        new_rank = _STATE_RANK.get(new_state, 1)

        if new_state == "healthy":
            change_type = "recovered"
            message = f"{new['label']} healthy"
            priority = Priority.HEALTHY
        elif new_rank > old_rank:
            change_type = "health_degraded"
            message = new["message"] or (
                f"{new['label']} {old_state} to {new_state}"
            )
            priority = _STATE_PRIORITY.get(
                new_state,
                Priority.WARNING,
            )
        else:
            change_type = "health_improved"
            message = new["message"] or (
                f"{new['label']} {old_state} to {new_state}"
            )
            priority = _STATE_PRIORITY.get(
                new_state,
                Priority.INFO,
            )

        return StorageHealthChange(
            change_type=change_type,
            device_key=key,
            label=new["label"],
            old_state=old_state,
            new_state=new_state,
            message=message,
            priority=priority,
            old=old,
            new=new,
        )

    def _counter_change(
        self,
        key: str,
        old: dict[str, Any],
        new: dict[str, Any],
    ) -> StorageHealthChange | None:
        increases = []

        for field in _COUNTER_FIELDS:
            old_value = old.get(field)
            new_value = new.get(field)

            if (
                old_value is not None
                and new_value is not None
                and new_value > old_value
            ):
                increases.append(
                    (field, old_value, new_value)
                )

        if not increases:
            return None

        labels = {
            "reallocated_sectors": "reallocated",
            "pending_sectors": "pending",
            "offline_uncorrectable": "uncorrectable",
            "interface_errors": "interface",
        }

        details = ", ".join(
            f"{labels[field]} {old_value}->{new_value}"
            for field, old_value, new_value in increases
        )

        media_failure = any(
            field in {
                "pending_sectors",
                "offline_uncorrectable",
            }
            for field, _, _ in increases
        )

        return StorageHealthChange(
            change_type="media_counter_increased",
            device_key=key,
            label=new["label"],
            old_state=old["state"],
            new_state=new["state"],
            message=details,
            priority=(
                Priority.CRITICAL
                if media_failure
                else Priority.WARNING
            ),
            old=old,
            new=new,
        )

    def _temperature_change(
        self,
        key: str,
        old: dict[str, Any],
        new: dict[str, Any],
    ) -> StorageHealthChange | None:
        old_temp = old.get("temperature_c")
        new_temp = new.get("temperature_c")

        if old_temp is None or new_temp is None:
            return None

        # State transitions already carry temperature threshold crossings.
        if old["state"] != new["state"]:
            return None

        # Avoid noise from normal one-degree movement. A jump of five or more
        # degrees is worth recording even if it remains within one state.
        if new_temp < old_temp + 5:
            return None

        return StorageHealthChange(
            change_type="temperature_increased",
            device_key=key,
            label=new["label"],
            old_state=old["state"],
            new_state=new["state"],
            message=f"temperature {old_temp}C->{new_temp}C",
            priority=(
                Priority.WARNING
                if new["state"] != "critical"
                else Priority.CRITICAL
            ),
            old=old,
            new=new,
        )

    @staticmethod
    def _ordered(
        changes: list[StorageHealthChange],
    ) -> list[StorageHealthChange]:
        return sorted(
            changes,
            key=lambda change: (
                -int(change.priority),
                change.label,
                change.change_type,
            ),
        )


class StorageEventRecorder:
    """
    Append storage-health events to a replayable JSONL journal.
    """

    def __init__(
        self,
        path: str | Path = (
            "development/logs/storage_events/events.jsonl"
        ),
    ) -> None:
        self.path = Path(path)

    def record(
        self,
        change: StorageHealthChange,
        event: MissionEvent,
    ) -> None:
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        payload = {
            "recorded_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "change": {
                **asdict(change),
                "priority": int(change.priority),
                "priority_name": change.priority.name,
            },
            "event": {
                **asdict(event),
                "priority": int(event.priority),
                "priority_name": event.priority.name,
                "category": event.category.value,
            },
        }

        with self.path.open(
            "a",
            encoding="utf-8",
        ) as stream:
            stream.write(
                json.dumps(
                    payload,
                    sort_keys=True,
                )
            )
            stream.write("\n")


LOGGER = logging.getLogger(__name__)


class StorageHealthWatcher:
    """
    Poll storage health and emit only meaningful state changes.

    Events are queued internally because Mission Control's current watcher
    contract returns at most one event per evaluation cycle.
    """

    def __init__(
        self,
        *,
        manager: HardwareManager | None = None,
        report_provider: ReportProvider | None = None,
        differ: StorageHealthDiffer | None = None,
        recorder: StorageEventRecorder | None = None,
        event_observers=None,
        interval: float = 300.0,
        clock: Clock = time.monotonic,
        emit_initial_conditions: bool = True,
    ) -> None:
        self.manager = manager
        self.report_provider = (
            report_provider
            or self._build_report
        )
        self.differ = differ or StorageHealthDiffer()
        self.recorder = recorder
        self.event_observers = tuple(
            event_observers or ()
        )
        self.interval = max(float(interval), 0.0)
        self.clock = clock
        self.emit_initial_conditions = emit_initial_conditions

        self._snapshot: dict[str, dict[str, Any]] | None = None
        self._pending: deque[MissionEvent] = deque()
        self._last_poll: float | None = None

    def _build_report(self) -> HealthReport:
        manager = self.manager or HardwareManager()
        self.manager = manager
        return build_health_report(manager)

    def __call__(
        self,
        state: Mapping[str, Any] | None = None,
    ) -> MissionEvent | None:
        del state

        if self._pending:
            return self._pending.popleft()

        now = self.clock()

        if (
            self._last_poll is not None
            and now - self._last_poll < self.interval
        ):
            return None

        self._last_poll = now
        self.poll()

        if self._pending:
            return self._pending.popleft()

        return None

    def poll(self) -> list[MissionEvent]:
        report = self.report_provider()
        current = self.differ.snapshot(report)

        if self._snapshot is None:
            changes = (
                self.differ.initial_changes(current)
                if self.emit_initial_conditions
                else []
            )
        else:
            changes = self.differ.compare(
                self._snapshot,
                current,
            )

        self._snapshot = current

        events = []

        for change in changes:
            event = change.to_event()
            events.append(event)
            self._pending.append(event)

            for observer in self.event_observers:
                try:
                    observer(event)
                except Exception:
                    LOGGER.exception(
                        "Storage event observer failed: %s",
                        event.event_id,
                    )

            if self.recorder is not None:
                self.recorder.record(change, event)

        return events

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def reset(self) -> None:
        self._snapshot = None
        self._pending.clear()
        self._last_poll = None


__all__ = [
    "StorageEventRecorder",
    "StorageHealthChange",
    "StorageHealthDiffer",
    "StorageHealthWatcher",
]
