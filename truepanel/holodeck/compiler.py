"""Compile privacy-safe Black Box incidents into minimal regression data."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from truepanel.history.black_box import (
    BlackBoxFrame,
    BlackBoxRecorder,
    BlackBoxReplay,
    sanitize_black_box_value,
)

ViolationEvaluator = Callable[[Sequence[BlackBoxFrame]], bool]


class CompiledIncident:
    """Defensively copied, data-only output from the Incident Compiler."""

    def __init__(self, scenario: dict[str, Any], manifest: dict[str, Any]):
        self._scenario = copy.deepcopy(scenario)
        self._manifest = copy.deepcopy(manifest)

    @property
    def scenario(self) -> dict[str, Any]:
        return copy.deepcopy(self._scenario)

    @property
    def manifest(self) -> dict[str, Any]:
        return copy.deepcopy(self._manifest)

    def as_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "manifest": self.manifest,
        }


class IncidentCompiler:
    """Minimize a recorded invariant violation with a fixed work budget.

    The evaluator returns ``True`` when the supplied ordered frames still
    reproduce the violation. It receives fresh defensive frame copies on
    every call, so even a stateful or destructive evaluator cannot alter the
    source replay or the compiler's candidate.
    """

    def __init__(
        self,
        evaluator: ViolationEvaluator,
        *,
        invariant_id: str,
        max_evaluations: int = 1_000,
        max_frames: int = 10_000,
    ) -> None:
        if not callable(evaluator):
            raise TypeError("Incident Compiler evaluator must be callable")
        if not str(invariant_id).strip():
            raise ValueError("Incident Compiler invariant_id is required")
        self.evaluator = evaluator
        self.invariant_id = str(invariant_id).strip()
        self.max_evaluations = max(1, int(max_evaluations))
        self.max_frames = max(1, int(max_frames))
        self.evaluations = 0
        self.budget_exhausted = False

    @staticmethod
    def _load(
        source: BlackBoxReplay | BlackBoxRecorder | str | Path,
    ) -> BlackBoxReplay:
        if isinstance(source, BlackBoxReplay):
            return source
        if isinstance(source, BlackBoxRecorder):
            return source.load_replay()
        if isinstance(source, (str, Path)):
            return BlackBoxRecorder(source).load_replay()
        raise TypeError("source must be a BlackBoxReplay, recorder, or recording path")

    def _violates(self, frames: Sequence[BlackBoxFrame]) -> bool | None:
        if self.evaluations >= self.max_evaluations:
            self.budget_exhausted = True
            return None
        self.evaluations += 1
        isolated = tuple(frame.copy() for frame in frames)
        return bool(self.evaluator(isolated))

    def _smallest_window(
        self,
        frames: tuple[BlackBoxFrame, ...],
    ) -> tuple[BlackBoxFrame, ...]:
        """Find the earliest shortest contiguous reproducing window."""

        count = len(frames)
        for length in range(1, count + 1):
            for start in range(0, count - length + 1):
                candidate = frames[start : start + length]
                result = self._violates(candidate)
                if result is None:
                    return frames
                if result:
                    return candidate
        return frames

    def _minimize_subset(
        self,
        frames: tuple[BlackBoxFrame, ...],
    ) -> tuple[BlackBoxFrame, ...]:
        """Apply deterministic delta debugging, then a one-frame sweep."""

        candidate = frames
        granularity = 2
        while len(candidate) >= 2:
            chunk_size = (len(candidate) + granularity - 1) // granularity
            reduced = False
            for start in range(0, len(candidate), chunk_size):
                trial = candidate[:start] + candidate[start + chunk_size :]
                if not trial:
                    continue
                result = self._violates(trial)
                if result is None:
                    return candidate
                if result:
                    candidate = trial
                    granularity = max(2, granularity - 1)
                    reduced = True
                    break
            if reduced:
                continue
            if granularity >= len(candidate):
                break
            granularity = min(len(candidate), granularity * 2)

        index = 0
        while index < len(candidate) and len(candidate) > 1:
            trial = candidate[:index] + candidate[index + 1 :]
            result = self._violates(trial)
            if result is None:
                break
            if result:
                candidate = trial
            else:
                index += 1
        return candidate

    def compile(
        self,
        source: BlackBoxReplay | BlackBoxRecorder | str | Path,
        *,
        name: str = "black-box-incident",
        host: str = "battlestation",
    ) -> CompiledIncident:
        replay = self._load(source)
        original = replay.frames
        if not original:
            raise ValueError("Incident Compiler requires at least one frame")
        if len(original) > self.max_frames:
            raise ValueError(
                f"Incident Compiler frame limit exceeded: {len(original)} > {self.max_frames}"
            )

        self.evaluations = 0
        self.budget_exhausted = False
        if not self._violates(original):
            raise ValueError("recording does not reproduce the requested invariant violation")

        window = self._smallest_window(original)
        minimized = self._minimize_subset(window)
        origin = minimized[0].captured_at
        compiled_frames = []
        for frame in minimized:
            payload = frame.as_dict()
            payload["at"] = frame.captured_at - origin
            payload.pop("captured_at", None)
            compiled_frames.append(payload)

        scenario = sanitize_black_box_value(
            {
                "schema_version": 1,
                "kind": "truepanel.holodeck.black_box_incident",
                "name": str(name).strip() or "black-box-incident",
                "host": str(host).strip() or "battlestation",
                "privacy": "sanitized",
                "time_origin": origin,
                "frames": compiled_frames,
            }
        )
        canonical = json.dumps(
            scenario,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        manifest = {
            "schema_version": 1,
            "kind": "truepanel.holodeck.regression_manifest",
            "invariant_id": self.invariant_id,
            "expected_violation": True,
            "privacy": "sanitized",
            "original_frame_count": len(original),
            "window_frame_count": len(window),
            "minimized_frame_count": len(minimized),
            "source_sequences": [frame.sequence for frame in minimized],
            "start_at": minimized[0].captured_at,
            "end_at": minimized[-1].captured_at,
            "duration_seconds": minimized[-1].captured_at - minimized[0].captured_at,
            "evaluations": self.evaluations,
            "max_evaluations": self.max_evaluations,
            "budget_exhausted": self.budget_exhausted,
            "scenario_sha256": hashlib.sha256(canonical).hexdigest(),
            "executable_code_generated": False,
        }
        return CompiledIncident(scenario, manifest)


__all__ = ["CompiledIncident", "IncidentCompiler", "ViolationEvaluator"]
