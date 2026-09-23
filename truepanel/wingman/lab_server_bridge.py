"""Offline-only internal status composer bridge for WINGMAN's HOLD view.

Not attached to any production route. A caller must supply the internal
MissionControlRequestHandler._compose_status_payload callable, not a client
request, HTTP response, recording, or cached snapshot. This bridge validates
both snapshot age and AEGIS's independent source-sampling metadata. A new
wrapper around stale evidence does not renew the evidence's age.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from copy import deepcopy
from typing import Any

from .service import WingmanServiceResult
from .trusted_snapshot_gate import TrustedSnapshotGate


class LabServerHoldBridge:
    """Read-only synthetic server composition test, not production wiring."""

    def __init__(
        self,
        *,
        internal_compose: Callable[[], dict[str, Any]],
        wall_clock: Callable[[], float] = time.time,
        monotonic_clock: Callable[[], float] = time.monotonic,
        maximum_source_age_seconds: float = 5.0,
    ) -> None:
        if not callable(internal_compose) or not callable(wall_clock):
            raise ValueError("Internal composer and clock must be callable")
        if (
            isinstance(maximum_source_age_seconds, bool)
            or not isinstance(maximum_source_age_seconds, (int, float))
            or not math.isfinite(maximum_source_age_seconds)
            or not 0 < maximum_source_age_seconds <= 5
        ):
            raise ValueError("Maximum source age must be within 0 to 5 seconds")
        self._compose = internal_compose
        self._wall_clock = wall_clock
        self._source_age = float(maximum_source_age_seconds)
        self._gate = TrustedSnapshotGate(
            composer=self._verified_compose,
            max_age_seconds=self._source_age,
            clock=monotonic_clock,
        )

    @staticmethod
    def _finite_timestamp(value: Any, field: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{field} is not a numeric timestamp")
        result = float(value)
        if not math.isfinite(result):
            raise ValueError(f"{field} is not finite")
        return result

    def _verified_compose(self) -> dict[str, Any]:
        snapshot = self._compose()
        if not isinstance(snapshot, dict):
            raise ValueError("Internal composer returned invalid status")
        now = self._finite_timestamp(self._wall_clock(), "wall_clock")
        composed_at = self._finite_timestamp(
            snapshot.get("timestamp"), "snapshot.timestamp"
        )
        reliability = snapshot.get("reliability")
        sampling = (
            reliability.get("sampling") if isinstance(reliability, dict) else None
        )
        if not isinstance(sampling, dict):
            raise ValueError("AEGIS source-sampling provenance absent")
        source_at = self._finite_timestamp(
            sampling.get("source_timestamp"), "sampling.source_timestamp"
        )
        sampled_at = self._finite_timestamp(
            sampling.get("sampled_at"), "sampling.sampled_at"
        )
        if sampling.get("fresh_sample") is not True:
            raise ValueError("AEGIS status reused an old sampling window")
        for stamp in (composed_at, source_at, sampled_at):
            age = now - stamp
            if age < 0 or age > self._source_age:
                raise ValueError("Snapshot or authoritative source is stale")
        if not (sampled_at <= source_at <= composed_at):
            raise ValueError("AEGIS source sampling chronology invalid")

        isolated = deepcopy(snapshot)
        # Lifeline session state is persisted. Its identity is not certified
        # fresh merely because this status response has a new timestamp.
        # Until an independently timestamped live inventory witness is wired,
        # this bridge refuses to publish a specific physical bay.
        isolated.pop("lifeline", None)
        return isolated

    def hold_view(self, model_result: WingmanServiceResult) -> dict[str, Any]:
        """Fresh internal composition only; accepts no user-supplied status."""
        ticket = self._gate.capture()
        return self._gate.project(model_result, ticket=ticket)


__all__ = ["LabServerHoldBridge"]
