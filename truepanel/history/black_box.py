"""Privacy-safe record and replay primitives for TruePanel Black Box."""

from __future__ import annotations

import ipaddress
import json
import re
from bisect import bisect_right
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping


BLACK_BOX_SCHEMA_VERSION = 1
REDACTED = "<redacted>"

_SENSITIVE_KEYS = {
    "address",
    "email",
    "hostname",
    "host_name",
    "ip",
    "ip_address",
    "mac",
    "mac_address",
    "password",
    "path",
    "serial",
    "serial_number",
    "token",
    "username",
    "user",
    "uuid",
    "wwid",
    "wwn",
}

_MAC_RE = re.compile(
    r"(?i)(?<![0-9a-f])(?:[0-9a-f]{2}:){5}[0-9a-f]{2}(?![0-9a-f])"
)
_IPV4_CANDIDATE_RE = re.compile(
    r"(?<![0-9.])(?:\d{1,3}\.){3}\d{1,3}(?![0-9.])"
)
_UUID_RE = re.compile(
    r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}\b"
)


def _normalized_key(key: object) -> str:
    return str(key).strip().lower().replace("-", "_")


def _key_is_sensitive(key: object) -> bool:
    normalized = _normalized_key(key)
    if normalized in _SENSITIVE_KEYS:
        return True

    suffixes = (
        "_hostname",
        "_ip",
        "_ip_address",
        "_mac",
        "_mac_address",
        "_password",
        "_path",
        "_serial",
        "_serial_number",
        "_token",
        "_username",
        "_uuid",
        "_wwid",
        "_wwn",
    )
    return normalized.endswith(suffixes)


def _redact_string(value: str) -> str:
    value = _MAC_RE.sub(REDACTED, value)
    value = _UUID_RE.sub(REDACTED, value)

    def replace_ipv4(match: re.Match[str]) -> str:
        candidate = match.group(0)
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            return candidate
        return REDACTED

    return _IPV4_CANDIDATE_RE.sub(replace_ipv4, value)


def sanitize_black_box_value(value: Any) -> Any:
    """Return a JSON-safe, privacy-sanitized copy of *value*.

    Sensitive mapping keys are retained with a redaction marker so replay can
    distinguish "known but hidden" from "not collected". String values are
    scrubbed for IP, MAC, and UUID literals even when they occur in LCD text or
    alert messages.
    """

    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, nested in value.items():
            string_key = str(key)
            sanitized[string_key] = (
                REDACTED
                if _key_is_sensitive(key)
                else sanitize_black_box_value(nested)
            )
        return sanitized

    if isinstance(value, (list, tuple)):
        return [sanitize_black_box_value(item) for item in value]

    if isinstance(value, str):
        return _redact_string(value)

    if value is None or isinstance(value, (bool, int, float)):
        return value

    return _redact_string(str(value))


@dataclass(frozen=True)
class BlackBoxFrame:
    """One privacy-safe point-in-time TruePanel state capture."""

    captured_at: float
    sequence: int
    telemetry: dict[str, Any] = field(default_factory=dict)
    lcd: dict[str, Any] = field(default_factory=dict)
    fan: dict[str, Any] = field(default_factory=dict)
    storage: dict[str, Any] = field(default_factory=dict)
    alerts: list[dict[str, Any]] = field(default_factory=list)
    buttons: dict[str, Any] = field(default_factory=dict)
    mission_control: dict[str, Any] = field(default_factory=dict)
    schema_version: int = BLACK_BOX_SCHEMA_VERSION
    privacy: str = "sanitized"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def copy(self) -> "BlackBoxFrame":
        """Return a deep, revalidated copy suitable for replay isolation."""

        return type(self).from_dict(self.as_dict())

    @classmethod
    def capture(
        cls,
        *,
        captured_at: float,
        sequence: int,
        telemetry: Mapping[str, Any] | None = None,
        lcd: Mapping[str, Any] | None = None,
        fan: Mapping[str, Any] | None = None,
        storage: Mapping[str, Any] | None = None,
        alerts: Iterable[Mapping[str, Any]] | None = None,
        buttons: Mapping[str, Any] | None = None,
        mission_control: Mapping[str, Any] | None = None,
    ) -> "BlackBoxFrame":
        payload = sanitize_black_box_value(
            {
                "telemetry": dict(telemetry or {}),
                "lcd": dict(lcd or {}),
                "fan": dict(fan or {}),
                "storage": dict(storage or {}),
                "alerts": [dict(item) for item in alerts or ()],
                "buttons": dict(buttons or {}),
                "mission_control": dict(mission_control or {}),
            }
        )

        return cls(
            captured_at=float(captured_at),
            sequence=max(0, int(sequence)),
            telemetry=payload["telemetry"],
            lcd=payload["lcd"],
            fan=payload["fan"],
            storage=payload["storage"],
            alerts=payload["alerts"],
            buttons=payload["buttons"],
            mission_control=payload["mission_control"],
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BlackBoxFrame":
        schema_version = int(data.get("schema_version", 0))
        if schema_version != BLACK_BOX_SCHEMA_VERSION:
            raise ValueError(
                "unsupported Black Box schema version: "
                f"{schema_version}"
            )

        if data.get("privacy") != "sanitized":
            raise ValueError("Black Box frame is not marked sanitized")

        return cls.capture(
            captured_at=float(data["captured_at"]),
            sequence=int(data["sequence"]),
            telemetry=data.get("telemetry", {}),
            lcd=data.get("lcd", {}),
            fan=data.get("fan", {}),
            storage=data.get("storage", {}),
            alerts=data.get("alerts", []),
            buttons=data.get("buttons", {}),
            mission_control=data.get("mission_control", {}),
        )


class BlackBoxRecorder:
    """Append and replay sanitized Black Box frames as compact JSONL."""

    def __init__(
        self,
        path: str | Path,
        *,
        max_frame_bytes: int = 262_144,
    ):
        self.path = Path(path)
        self.max_frame_bytes = max(1_024, int(max_frame_bytes))

    def append(self, frame: BlackBoxFrame) -> int:
        if not isinstance(frame, BlackBoxFrame):
            raise TypeError("frame must be a BlackBoxFrame")

        encoded = json.dumps(
            frame.as_dict(),
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

        if len(encoded) > self.max_frame_bytes:
            raise ValueError(
                "Black Box frame exceeds maximum size: "
                f"{len(encoded)} > {self.max_frame_bytes} bytes"
            )

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("ab") as handle:
            handle.write(encoded + b"\n")

        return len(encoded)

    def replay(self) -> Iterable[BlackBoxFrame]:
        if not self.path.exists():
            return

        with self.path.open(
            "r",
            encoding="utf-8",
            errors="strict",
        ) as handle:
            for line_number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                    yield BlackBoxFrame.from_dict(data)
                except Exception as error:
                    raise ValueError(
                        "invalid Black Box frame at line "
                        f"{line_number}: {error}"
                    ) from error

    def load_replay(self) -> "BlackBoxReplay":
        """Load this recording into a validated deterministic replay."""

        return BlackBoxReplay(self.replay())


class BlackBoxReplay:
    """Validated, deterministic view over an ordered Black Box recording.

    Replay deliberately has no wall-clock sleeps and performs no runtime or
    hardware operations. Consumers such as tests and a future Digital Twin can
    decide how quickly to advance through the immutable frame sequence.

    The replay owns defensive copies of input frames and returns defensive
    copies from every public frame accessor. Mutating a caller-owned frame or a
    frame returned from replay therefore cannot alter the stored recording.
    """

    def __init__(self, frames: Iterable[BlackBoxFrame]):
        copied_frames: list[BlackBoxFrame] = []
        for index, frame in enumerate(frames):
            if not isinstance(frame, BlackBoxFrame):
                raise TypeError(
                    f"replay frame {index} is not a BlackBoxFrame"
                )
            copied_frames.append(frame.copy())

        self._frames = tuple(copied_frames)

        previous_sequence: int | None = None
        previous_time: float | None = None

        for frame in self._frames:
            if (
                previous_sequence is not None
                and frame.sequence <= previous_sequence
            ):
                raise ValueError(
                    "Black Box replay sequences must increase strictly"
                )

            if (
                previous_time is not None
                and frame.captured_at < previous_time
            ):
                raise ValueError(
                    "Black Box replay timestamps must not move backward"
                )

            previous_sequence = frame.sequence
            previous_time = frame.captured_at

        self._times = tuple(
            frame.captured_at
            for frame in self._frames
        )
        self._sequence_index = {
            frame.sequence: index
            for index, frame in enumerate(self._frames)
        }

    @property
    def frames(self) -> tuple[BlackBoxFrame, ...]:
        return tuple(frame.copy() for frame in self._frames)

    @property
    def duration_seconds(self) -> float:
        if len(self._frames) < 2:
            return 0.0
        return (
            self._frames[-1].captured_at
            - self._frames[0].captured_at
        )

    def __len__(self) -> int:
        return len(self._frames)

    def at_sequence(
        self,
        sequence: int,
    ) -> BlackBoxFrame | None:
        index = self._sequence_index.get(int(sequence))
        if index is None:
            return None
        return self._frames[index].copy()

    def at_or_before(
        self,
        captured_at: float,
    ) -> BlackBoxFrame | None:
        """Return the latest frame at or before the requested timestamp."""

        index = bisect_right(
            self._times,
            float(captured_at),
        ) - 1

        if index < 0:
            return None

        return self._frames[index].copy()

    def between(
        self,
        start_at: float,
        end_at: float,
    ) -> tuple[BlackBoxFrame, ...]:
        """Return frames in the inclusive timestamp window."""

        start = float(start_at)
        end = float(end_at)

        if end < start:
            raise ValueError(
                "Black Box replay window end precedes start"
            )

        return tuple(
            frame.copy()
            for frame in self._frames
            if start <= frame.captured_at <= end
        )

    def cursor(
        self,
        *,
        start_index: int = 0,
    ) -> "BlackBoxReplayCursor":
        return BlackBoxReplayCursor(
            self,
            start_index=start_index,
        )


class BlackBoxReplayCursor:
    """Small deterministic playback cursor for tests and UI consumers."""

    def __init__(
        self,
        replay: BlackBoxReplay,
        *,
        start_index: int = 0,
    ):
        if not isinstance(replay, BlackBoxReplay):
            raise TypeError("replay must be a BlackBoxReplay")

        self.replay = replay

        if not replay._frames:
            self.index = -1
            return

        index = int(start_index)
        if index < 0 or index >= len(replay):
            raise IndexError(
                "Black Box replay start index out of range"
            )

        self.index = index

    @property
    def current(self) -> BlackBoxFrame | None:
        if self.index < 0:
            return None
        return self.replay._frames[self.index].copy()

    def step(
        self,
        delta: int = 1,
    ) -> BlackBoxFrame | None:
        if not self.replay._frames:
            return None

        target = min(
            max(self.index + int(delta), 0),
            len(self.replay) - 1,
        )
        self.index = target
        return self.current

    def seek_sequence(
        self,
        sequence: int,
    ) -> BlackBoxFrame | None:
        index = self.replay._sequence_index.get(int(sequence))
        if index is None:
            return None

        self.index = index
        return self.current

    def seek_time(
        self,
        captured_at: float,
    ) -> BlackBoxFrame | None:
        frame = self.replay.at_or_before(captured_at)
        if frame is None:
            return None

        self.index = self.replay._sequence_index[frame.sequence]
        return frame

    def remaining(self) -> Iterator[BlackBoxFrame]:
        """Iterate from the current frame through the end without moving."""

        if self.index < 0:
            return iter(())

        return iter(
            tuple(
                frame.copy()
                for frame in self.replay._frames[self.index:]
            )
        )
