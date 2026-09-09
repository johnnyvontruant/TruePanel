"""Read-only TrueNAS topology evidence for Project SENTINEL.

The provider deliberately uses supported TrueNAS middleware calls through
``midclt`` and normalizes only evidence returned by those calls. Application to
dataset relationships are emitted only when an application payload contains a
literal ``/mnt/...`` path that falls beneath a dataset mountpoint.
"""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable
from copy import deepcopy
from pathlib import PurePosixPath
from typing import Any


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _property_value(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("value")
    return value


def _normalize_path(value: Any) -> str | None:
    text = _text(value)
    if not text.startswith("/mnt/"):
        return None
    try:
        return str(PurePosixPath(text))
    except (TypeError, ValueError):
        return None


def _walk_paths(value: Any) -> set[str]:
    """Return literal TrueNAS mount paths present in a nested API payload."""

    paths: set[str] = set()

    if isinstance(value, dict):
        for item in value.values():
            paths.update(_walk_paths(item))
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            paths.update(_walk_paths(item))
    elif isinstance(value, str):
        path = _normalize_path(value)
        if path is not None:
            paths.add(path)

    return paths


def _path_within(path: str, mountpoint: str) -> bool:
    try:
        candidate = PurePosixPath(path)
        parent = PurePosixPath(mountpoint)
        candidate.relative_to(parent)
    except ValueError:
        return False
    return True


class MidcltClient:
    """Minimal JSON wrapper around the supported TrueNAS ``midclt`` CLI."""

    def __init__(
        self,
        *,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        timeout: float = 8.0,
    ) -> None:
        self.runner = runner
        self.timeout = float(timeout)

    def call(self, method: str, *arguments: Any) -> Any:
        command = ["midclt", "call", method]
        command.extend(
            json.dumps(argument, separators=(",", ":"))
            for argument in arguments
        )

        result = self.runner(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )
        return json.loads(result.stdout or "null")


class TopologyResolver:
    """Resolve datasets, applications, and proven storage dependencies."""

    def __init__(self, client: Any | None = None) -> None:
        self.client = client or MidcltClient()

    def _datasets(self) -> list[dict[str, Any]]:
        payload = self.client.call(
            "pool.dataset.query",
            [],
            {
                "extra": {
                    "flat": True,
                    "retrieve_children": True,
                    "retrieve_user_props": False,
                    "properties": ["mountpoint"],
                }
            },
        )

        result = []
        for item in _list(payload):
            if not isinstance(item, dict):
                continue

            dataset_id = _text(item.get("id"))
            pool = _text(item.get("pool"))
            if not dataset_id or not pool:
                continue

            mountpoint = _normalize_path(
                _property_value(item.get("mountpoint"))
            )

            result.append(
                {
                    "id": dataset_id,
                    "name": _text(item.get("name")) or dataset_id,
                    "pool": pool,
                    "type": _text(item.get("type")) or "UNKNOWN",
                    "mountpoint": mountpoint,
                    "locked": item.get("locked"),
                }
            )

        return sorted(result, key=lambda item: item["id"])

    def _applications(self) -> list[dict[str, Any]]:
        # TrueNAS 25.10 returns active workload and literal host-mount
        # evidence from the supported plain app.query response. Passing the
        # older retrieve_config option is rejected on BattleStation 25.10.5.
        payload = self.client.call(
            "app.query",
            [],
        )

        result = []
        for item in _list(payload):
            if not isinstance(item, dict):
                continue

            app_id = _text(item.get("id") or item.get("name"))
            if not app_id:
                continue

            paths = sorted(_walk_paths(item))
            result.append(
                {
                    "id": app_id,
                    "name": _text(item.get("name")) or app_id,
                    "state": _text(item.get("state")) or "UNKNOWN",
                    "paths": paths,
                }
            )

        return sorted(result, key=lambda item: item["id"])

    @staticmethod
    def _relationships(
        datasets: list[dict[str, Any]],
        applications: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        mounted = [
            item
            for item in datasets
            if _text(item.get("mountpoint"))
        ]
        mounted.sort(
            key=lambda item: len(_text(item.get("mountpoint"))),
            reverse=True,
        )

        result: set[tuple[str, str, str, str]] = set()

        for application in applications:
            app_id = _text(application.get("id"))
            for path in _list(application.get("paths")):
                path_text = _text(path)
                if not app_id or not path_text:
                    continue

                for dataset in mounted:
                    mountpoint = _text(dataset.get("mountpoint"))
                    if not _path_within(path_text, mountpoint):
                        continue

                    result.add(
                        (
                            _text(dataset.get("id")),
                            app_id,
                            path_text,
                            mountpoint,
                        )
                    )
                    # Longest mountpoint wins. A path proves its nearest
                    # dataset, not every ancestor dataset above it.
                    break

        return [
            {
                "dataset_id": dataset_id,
                "application_id": application_id,
                "path": path,
                "mountpoint": mountpoint,
                "source": "truenas.app.query.literal_path",
            }
            for dataset_id, application_id, path, mountpoint in sorted(result)
        ]

    def snapshot(self) -> dict[str, Any]:
        datasets = self._datasets()
        applications = self._applications()
        relationships = self._relationships(datasets, applications)

        return {
            "schema_version": 1,
            "read_only": True,
            "source": "truenas.middleware",
            "datasets": datasets,
            "applications": applications,
            "relationships": relationships,
        }


class CachedTopologyProvider:
    """Bound middleware cost while keeping topology evidence reasonably fresh."""

    def __init__(
        self,
        resolver: TopologyResolver | None = None,
        *,
        cache_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.resolver = resolver or TopologyResolver()
        self.cache_seconds = max(0.0, float(cache_seconds))
        self.clock = clock
        self._cached_at: float | None = None
        self._cached_payload: dict[str, Any] | None = None

    def snapshot(self) -> dict[str, Any]:
        now = self.clock()
        if (
            self._cached_at is not None
            and self._cached_payload is not None
            and now - self._cached_at < self.cache_seconds
        ):
            return deepcopy(self._cached_payload)

        payload = self.resolver.snapshot()
        if not isinstance(payload, dict):
            raise TypeError("SENTINEL topology resolver returned non-dict payload")

        self._cached_at = now
        self._cached_payload = deepcopy(payload)
        return deepcopy(payload)
