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

from .current_identity_witness import CurrentDriveWitness
from .service import WingmanServiceResult
from .trusted_snapshot_gate import InternalStatusCapture, TrustedSnapshotGate


class LabServerHoldBridge:
    """Read-only synthetic server composition test, not production wiring."""

    def __init__(
        self,
        *,
        internal_compose: Callable[[], dict[str, Any]],
        wall_clock: Callable[[], float] = time.time,
        monotonic_clock: Callable[[], float] = time.monotonic,
        maximum_source_age_seconds: float = 5.0,
        current_identity_observer: Callable[[], CurrentDriveWitness | None] | None = None,
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
        if current_identity_observer is not None and not callable(
            current_identity_observer
        ):
            raise ValueError("Live identity observer must be callable")
        self._compose = internal_compose
        self._identity_observer = current_identity_observer
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

    def _verified_compose(self) -> InternalStatusCapture:
        snapshot = self._compose()
        if not isinstance(snapshot, dict):
            raise ValueError("Internal composer returned invalid status")
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

        # A future trusted observer must perform an independent *current*
        # hardware read, never replay session metadata or copy a snapshot
        # timestamp. Nothing in this isolated module reads NAS hardware.
        witness = None
        if self._identity_observer is not None:
            try:
                candidate = self._identity_observer()
                if type(candidate) is CurrentDriveWitness:
                    witness = candidate
            except (OSError, RuntimeError, TypeError, ValueError, AttributeError):
                pass

        now = self._finite_timestamp(self._wall_clock(), "wall_clock")
        for stamp in (composed_at, source_at, sampled_at):
            age = now - stamp
            if age < 0 or age > self._source_age:
                raise ValueError("Snapshot or authoritative source is stale")
        if not (sampled_at <= source_at <= composed_at):
            raise ValueError("AEGIS source sampling chronology invalid")

        isolated = deepcopy(snapshot)
        # Persisted Lifeline facts are considered only when corroborated by
        # a separate and fresh current observation in this exact capture.
        if witness is None or not (
            composed_at <= witness.observed_at <= now
            and source_at <= witness.observed_at
            and now - witness.observed_at <= self._source_age
        ):
            witness = None
            isolated.pop("lifeline", None)
        return InternalStatusCapture(isolated, witness)

    def hold_view(self, model_result: WingmanServiceResult) -> dict[str, Any]:
        """Fresh internal composition only; model text is disabled in this lab."""
        del model_result
        ticket = self._gate.capture()
        return self._gate.project(
            WingmanServiceResult(
                status="MODEL_UNAVAILABLE",
                advisory=None,
                source_ids=(),
                errors=("LabGenerationDisabled",),
            ),
            ticket=ticket,
        )


__all__ = ["LabServerHoldBridge"]
