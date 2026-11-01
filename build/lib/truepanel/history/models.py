"""
TruePanel historical telemetry models.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class TelemetrySample:
    timestamp: float
    hostname: str

    cpu_percent: float
    ram_percent: float

    hottest_temp: float
    hottest_drive: str

    pool_capacity: float
    pool_name: str
    pool_health: str

    network_download: float
    network_upload: float

    zfs_read: float
    zfs_write: float

    scrub_running: bool
    resilver_running: bool
    zfs_percent: float | None

    smart_problem_count: int
    alert_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TelemetrySample":
        fields = cls.__dataclass_fields__

        filtered = {
            key: data[key]
            for key in fields
            if key in data
        }

        return cls(**filtered)
