"""Read-only, deterministic inference readiness against existing launch policy.

A readiness report is observational, never a launch permit. Runtime.start()
must repeat the resource check immediately before any actual process spawn.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .runtime import HostResources, RuntimePolicy


@dataclass(frozen=True)
class FileAvailability:
    """Pure, injected file evidence; no path or local file metadata is emitted."""

    server_present: bool
    model_present: bool


def file_availability(server: Path, model: Path) -> FileAvailability:
    """Read two explicitly configured local paths without loading the model."""

    return FileAvailability(
        server_present=server.is_file(),
        model_present=model.is_file(),
    )


def inference_readiness(
    resources: HostResources | None,
    files: FileAvailability,
    policy: RuntimePolicy | None = None,
) -> dict[str, Any]:
    """Report all applicable launch blockers, without invoking inference."""

    policy = policy or RuntimePolicy()
    reasons: list[str] = []
    available_gib: float | None = None
    load_1m: float | None = None

    if resources is None:
        reasons.append("HOST_RESOURCES_UNAVAILABLE")
    else:
        available = resources.available_memory_bytes
        load = resources.load_1m
        if isinstance(available, bool) or not isinstance(available, int) or available < 0:
            reasons.append("MEMORY_READING_INVALID")
        else:
            available_gib = round(available / 1024**3, 3)
            if available < policy.minimum_available_memory_bytes:
                reasons.append("MEMORY_BELOW_POLICY")
        if isinstance(load, bool) or not isinstance(load, (int, float)) or not math.isfinite(load) or load < 0:
            reasons.append("LOAD_READING_INVALID")
        else:
            load_1m = round(load, 3)
            if load > policy.maximum_load_1m:
                reasons.append("LOAD_ABOVE_POLICY")

    if not files.server_present:
        reasons.append("LLAMA_SERVER_MISSING")
    if not files.model_present:
        reasons.append("MODEL_FILE_MISSING")

    return {
        "schema_version": 1,
        "project": "WINGMAN",
        "status": "HOLD" if reasons else "READY_FOR_RECHECK",
        "reason_codes": reasons,
        "available_memory_gib": available_gib,
        "minimum_memory_gib": round(policy.minimum_available_memory_bytes / 1024**3, 3),
        "load_1m": load_1m,
        "maximum_load_1m": policy.maximum_load_1m,
        "server_present": files.server_present,
        "model_present": files.model_present,
        "advisory_only": True,
        "control_authority": False,
        "production_mutation": False,
        "model_invoked": False,
        "launch_authorized": False,
    }


__all__ = ["FileAvailability", "file_availability", "inference_readiness"]
