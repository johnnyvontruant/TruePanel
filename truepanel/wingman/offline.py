"""Deterministic, model-free WINGMAN briefing from an allowlisted snapshot.

Only known status enums, bounded counts and verified pool labels enter prose.
No model, hardware provider, raw collector, external network, or action is used.
"""

from __future__ import annotations

import re
from typing import Any

from .storage_evidence import drive_health_evidence

_SAFE_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,47}$")
_POOL_STATES = frozenset(
    {"ONLINE", "DEGRADED", "FAULTED", "OFFLINE", "UNAVAIL", "REMOVED", "SUSPENDED"}
)
_HOLD_STATES = frozenset({"HOLD", "REVIEW"})


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _observation(text: str, source: str) -> dict[str, Any]:
    return {"text": text, "source_ids": [source]}


def offline_brief(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return bounded, evidence-cited observations; never infer overall health."""

    snapshot = _mapping(snapshot)
    observations: list[dict[str, Any]] = []
    uncertainty: list[str] = []
    storage = _mapping(snapshot.get("storage"))
    pools = storage.get("pools")
    if isinstance(pools, list) and pools:
        valid = 0
        for pool in pools[:8]:
            if not isinstance(pool, dict):
                uncertainty.append("A pool record was unavailable or malformed.")
                continue
            name = pool.get("name")
            state = pool.get("health") or pool.get("state")
            if (
                isinstance(name, str)
                and _SAFE_LABEL.fullmatch(name)
                and isinstance(state, str)
                and state.upper() in _POOL_STATES
            ):
                observations.append(
                    _observation(
                        f"Pool {name}: reported {state.upper()}.",
                        "status:storage",
                    )
                )
                valid += 1
            else:
                uncertainty.append("A pool name or state was not verified.")
        if len(pools) > 8:
            uncertainty.append("Additional pool records were not summarized.")
        if not valid:
            uncertainty.append("No recognized pool states were available.")
    else:
        uncertainty.append("Storage pool status is unavailable.")

    reliability = _mapping(snapshot.get("reliability"))
    state = reliability.get("state")
    if isinstance(state, str) and state.upper() in _HOLD_STATES:
        observations.append(
            _observation(f"AEGIS reports {state.upper()}; this briefing cannot clear it.", "status:reliability")
        )
    elif state is None or reliability.get("unavailable") is True:
        uncertainty.append("AEGIS reliability state is unavailable.")
    elif isinstance(state, str) and state.upper() in {"UNKNOWN", "UNAVAILABLE"}:
        uncertainty.append("AEGIS reliability state is unknown.")
    # Do not translate an unrecognized or non-HOLD state into a healthy verdict.

    guidance = snapshot.get("operator_guidance")
    if isinstance(guidance, list):
        held = 0
        review = 0
        for item in guidance:
            if not isinstance(item, dict):
                continue
            marker = item.get("status") or item.get("state")
            if isinstance(marker, str) and marker.upper() == "HOLD":
                held += 1
            elif isinstance(marker, str) and marker.upper() == "REVIEW":
                review += 1
        if held or review:
            observations.append(
                _observation(
                    f"Operator guidance includes {held} HOLD and {review} REVIEW entries; existing gates remain in force.",
                    "status:operator_guidance",
                )
            )

    # Pool ONLINE is not a clearance for individual drives. Give verified
    # drive-health concerns space in the brief before routine pool states.
    drive_observations, drive_uncertainty = drive_health_evidence(storage)
    uncertainty.extend(drive_uncertainty)
    safety = [
        item for item in observations
        if item["source_ids"][0] in {
            "status:reliability", "status:operator_guidance"
        }
    ]
    ordinary = [item for item in observations if item not in safety]
    prioritized = safety + drive_observations + ordinary

    if not prioritized:
        summary = "No verified instrument observations are available."
        status = "INSUFFICIENT_EVIDENCE"
    else:
        summary = " ".join(item["text"] for item in prioritized[:3])
        status = "OBSERVED"

    visible = prioritized[:10]
    return {
        "schema_version": 1,
        "project": "WINGMAN",
        "mode": "offline_brief",
        "status": status,
        "summary": summary,
        "observations": visible,
        "source_ids": list(dict.fromkeys(
            source for item in visible for source in item["source_ids"]
        )),
        "uncertainty": list(dict.fromkeys(uncertainty))[:8],
        "advisory_only": True,
        "control_authority": False,
        "production_mutation": False,
        "model_invoked": False,
    }


__all__ = ["offline_brief"]
