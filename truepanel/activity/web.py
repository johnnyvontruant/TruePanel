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


def mission_control_activity(
    payload: Mapping[str, Any],
    *,
    providers: Iterable[ActivityProvider] = (),
) -> dict[str, object]:
    """Build a bounded, read-only activity block for Mission Control.

    ZFS consumes the storage evidence already present in the status snapshot.
    Optional providers can be injected by later integrations without changing
    the Mission Control contract. Registry/provider failures never escape into
    core health reporting.
    """

    status = payload if isinstance(payload, Mapping) else {}
    zfs = ZfsActivityProvider(lambda: _storage_zfs_activity(status))

    try:
        registry = ActivityRegistry([zfs, *tuple(providers)])
        result = registry.snapshot().as_dict()
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
