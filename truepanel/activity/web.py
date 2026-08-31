"""Mission Control presentation adapter for Project OBSERVATORY."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .provider import ActivityProvider
from .registry import REGISTRY_SCHEMA_VERSION, ActivityRegistry
from .zfs import ZfsActivityProvider


def _storage_zfs_activity(payload: Mapping[str, Any]) -> Any:
    storage = payload.get("storage")
    if not isinstance(storage, Mapping):
        return {}
    activity = storage.get("zfs_activity")
    return activity if isinstance(activity, Mapping) else {}


def _mission_control_observation(value: object) -> object:
    """Project normalized evidence into the privacy-safe cockpit contract."""

    if not isinstance(value, Mapping):
        return value
    observation = dict(value)
    if observation.get("source") != "plex":
        return observation

    state = str(observation.get("state", "")).lower()
    if state == "playing":
        title = "Plex playback"
    elif state == "paused":
        title = "Plex session paused"
    else:
        title = "Plex activity"

    observation["title"] = title
    observation["subtitle"] = "Media workload"
    observation["context"] = {}
    return observation


def _mission_control_registry(result: Mapping[str, object]) -> dict[str, object]:
    projected = dict(result)
    projected["observations"] = [
        _mission_control_observation(item)
        for item in result.get("observations", [])
        if isinstance(result.get("observations"), list)
    ]

    providers: list[object] = []
    raw_providers = result.get("providers", [])
    if isinstance(raw_providers, list):
        for value in raw_providers:
            if not isinstance(value, Mapping):
                providers.append(value)
                continue
            provider = dict(value)
            observations = provider.get("observations", [])
            if isinstance(observations, list):
                provider["observations"] = [
                    _mission_control_observation(item)
                    for item in observations
                ]
            providers.append(provider)
    projected["providers"] = providers
    return projected


def mission_control_activity(
    payload: Mapping[str, Any],
    *,
    providers: Iterable[ActivityProvider] = (),
) -> dict[str, object]:
    """Build a bounded, read-only activity block for Mission Control.

    ZFS consumes the storage evidence already present in the status snapshot.
    Optional providers can be injected by later integrations without changing
    the Mission Control contract. Registry/provider failures never escape into
    core health reporting. Provider-private presentation details are projected
    out before the block reaches the Mission Control API.
    """

    status = payload if isinstance(payload, Mapping) else {}
    zfs = ZfsActivityProvider(lambda: _storage_zfs_activity(status))

    try:
        registry = ActivityRegistry([zfs, *tuple(providers)])
        result = _mission_control_registry(registry.snapshot().as_dict())
        return {
            "project": "OBSERVATORY",
            "read_only": True,
            "production_mutation": False,
            **result,
        }
    except Exception:
        return {
            "schema_version": REGISTRY_SCHEMA_VERSION,
            "project": "OBSERVATORY",
            "read_only": True,
            "production_mutation": False,
            "providers": [],
            "observations": [],
            "truncated": False,
            "unavailable": True,
        }


__all__ = ["mission_control_activity"]
