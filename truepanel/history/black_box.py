"""Privacy-safe record and replay primitives for TruePanel Black Box."""

from __future__ import annotations

import ipaddress
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping


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

_MAC_RE = re.compile(r"(?i)(?<![0-9a-f])(?:[0-9a-f]{2}:){5}[0-9a-f]{2}(?![0-9a-f])")
_IPV4_CANDIDATE_RE = re.compile(r"(?<![0-9.])(?:\d{1,3}\.){3}\d{1,3}(?![0-9.])")
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

    def __init__(self, path: str | Path, *, max_frame_bytes: int = 262_144):
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

        with self.path.open("r", encoding="utf-8", errors="strict") as handle:
            for line_number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                    yield BlackBoxFrame.from_dict(data)
                except Exception as error:
                    raise ValueError(
                        f"invalid Black Box frame at line {line_number}: {error}"
                    ) from error
