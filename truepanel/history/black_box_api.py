"""Transport-neutral, read-only API contract for Black Box replay sessions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


BLACK_BOX_REPLAY_API_SCHEMA_VERSION = 1
MAX_TIMELINE_ITEMS = 512
MAX_INCIDENT_ITEMS = 512
MAX_SCENARIO_FAULTS = 64
SUPPORTED_SCENARIO_FAULTS = frozenset(
    {
        "fan_stall",
        "storage_degraded",
        "lcd_stale",
        "mission_control_unavailable",
    }
)


def _bounded_limit(value: int, *, maximum: int) -> int:
    limit = int(value)
    if limit < 1:
        raise ValueError("limit must be positive")
    return min(limit, maximum)


def _view_dict(view: Any) -> dict[str, Any]:
    payload = view.as_dict()
    if not isinstance(payload, dict):
        raise TypeError("replay view as_dict() must return a dict")
    return payload


def normalize_scenario_request(
    faults_by_sequence: Mapping[int, str],
) -> dict[int, str]:
    """Validate a bounded simulation-only chaos scenario request."""

    if not isinstance(faults_by_sequence, Mapping):
        raise TypeError("scenario faults must be a mapping")
    if len(faults_by_sequence) > MAX_SCENARIO_FAULTS:
        raise ValueError("scenario exceeds maximum fault count")

    normalized: dict[int, str] = {}
    for sequence, kind in faults_by_sequence.items():
        sequence_number = int(sequence)
        if sequence_number < 0:
            raise ValueError("scenario sequence must be non-negative")
        fault_kind = str(kind)
        if fault_kind not in SUPPORTED_SCENARIO_FAULTS:
            raise ValueError(f"unsupported Black Box chaos fault: {fault_kind}")
        normalized[sequence_number] = fault_kind
    return dict(sorted(normalized.items()))


@dataclass(frozen=True)
class BlackBoxReplayAPIMetadata:
    """Bounded browser-safe metadata for one offline replay session."""

    frame_count: int
    first_sequence: int | None
    last_sequence: int | None
    first_captured_at: float | None
    last_captured_at: float | None
    duration_seconds: float
    simulation_only: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": BLACK_BOX_REPLAY_API_SCHEMA_VERSION,
            "read_only": True,
            "frame_count": self.frame_count,
            "first_sequence": self.first_sequence,
            "last_sequence": self.last_sequence,
            "first_captured_at": self.first_captured_at,
            "last_captured_at": self.last_captured_at,
            "duration_seconds": self.duration_seconds,
            "simulation_only": self.simulation_only,
            "supported_scenario_faults": sorted(SUPPORTED_SCENARIO_FAULTS),
        }


class BlackBoxReplayAPI:
    """Expose an offline replay session through data-only response payloads.

    This is intentionally not an HTTP server. A future Mission Control route
    layer may serialize these payloads, but this object has no sockets, live
    providers, service control, hardware access, or callback execution path.
    """

    def __init__(self, session: Any):
        required = (
            "replay",
            "incidents",
            "simulation_only",
            "at_sequence",
            "at_or_before",
        )
        missing = [name for name in required if not hasattr(session, name)]
        if missing:
            raise TypeError(
                f"invalid Black Box replay session; missing={missing}"
            )
        self.session = session

    def metadata(self) -> dict[str, Any]:
        frames = self.session.replay.frames
        first = frames[0] if frames else None
        last = frames[-1] if frames else None
        return BlackBoxReplayAPIMetadata(
            frame_count=len(frames),
            first_sequence=None if first is None else first.sequence,
            last_sequence=None if last is None else last.sequence,
            first_captured_at=None if first is None else first.captured_at,
            last_captured_at=None if last is None else last.captured_at,
            duration_seconds=float(self.session.replay.duration_seconds),
            simulation_only=bool(self.session.simulation_only),
        ).as_dict()

    def frame(self, sequence: int) -> dict[str, Any] | None:
        view = self.session.at_sequence(int(sequence))
        return None if view is None else _view_dict(view)

    def seek(self, captured_at: float) -> dict[str, Any] | None:
        view = self.session.at_or_before(float(captured_at))
        return None if view is None else _view_dict(view)

    def timeline(
        self,
        *,
        start_sequence: int | None = None,
        end_sequence: int | None = None,
        limit: int = 256,
    ) -> dict[str, Any]:
        bounded = _bounded_limit(limit, maximum=MAX_TIMELINE_ITEMS)
        if (
            start_sequence is not None
            and end_sequence is not None
            and int(end_sequence) < int(start_sequence)
        ):
            raise ValueError("timeline end_sequence precedes start_sequence")

        items: list[dict[str, Any]] = []
        truncated = False
        for frame in self.session.replay.frames:
            if (
                start_sequence is not None
                and frame.sequence < int(start_sequence)
            ):
                continue
            if (
                end_sequence is not None
                and frame.sequence > int(end_sequence)
            ):
                continue
            if len(items) >= bounded:
                truncated = True
                break
            view = self.session.at_sequence(frame.sequence)
            if view is None:
                raise RuntimeError("replay session lost timeline sequence")
            items.append(_view_dict(view))

        return {
            "schema_version": BLACK_BOX_REPLAY_API_SCHEMA_VERSION,
            "read_only": True,
            "items": items,
            "count": len(items),
            "truncated": truncated,
        }

    def incident_history(self, *, limit: int = 256) -> dict[str, Any]:
        bounded = _bounded_limit(limit, maximum=MAX_INCIDENT_ITEMS)
        incidents = self.session.incidents
        selected = incidents[:bounded]
        return {
            "schema_version": BLACK_BOX_REPLAY_API_SCHEMA_VERSION,
            "read_only": True,
            "items": [incident.as_dict() for incident in selected],
            "count": len(selected),
            "truncated": len(incidents) > len(selected),
        }

    def scenario_contract(self) -> dict[str, Any]:
        return {
            "schema_version": BLACK_BOX_REPLAY_API_SCHEMA_VERSION,
            "read_only": True,
            "simulation_only": True,
            "max_faults": MAX_SCENARIO_FAULTS,
            "supported_faults": sorted(SUPPORTED_SCENARIO_FAULTS),
        }


__all__ = [
    "BLACK_BOX_REPLAY_API_SCHEMA_VERSION",
    "MAX_INCIDENT_ITEMS",
    "MAX_SCENARIO_FAULTS",
    "MAX_TIMELINE_ITEMS",
    "SUPPORTED_SCENARIO_FAULTS",
    "BlackBoxReplayAPI",
    "BlackBoxReplayAPIMetadata",
    "normalize_scenario_request",
]
