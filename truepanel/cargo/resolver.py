"""Resolve recent Sonarr and Radarr imports to their current media files.

Cargo discovery is deliberately read-only. Import history establishes that
cargo arrived; current Servarr metadata establishes where that same media
lives now. Historical file IDs are treated as evidence, not permanent truth.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class ServarrConfig:
    """Connection and path translation settings for one Servarr application."""

    name: str
    base_url: str
    config_path: Path
    media_prefix: str
    host_prefix: Path


class ServarrClient:
    """Small read-only Servarr API client."""

    def __init__(
        self,
        config: ServarrConfig,
        *,
        timeout: float = 5.0,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        self.config = config
        self.timeout = float(timeout)
        self.opener = opener

    def _api_key(self) -> str:
        root = ET.parse(self.config.config_path).getroot()
        key = str(root.findtext("ApiKey") or "").strip()

        if not key:
            raise RuntimeError(
                f"{self.config.name} API key unavailable"
            )

        return key

    def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = self.config.base_url.rstrip("/") + endpoint

        if params:
            url += "?" + urlencode(params)

        request = Request(
            url,
            headers={
                "X-Api-Key": self._api_key(),
                "Accept": "application/json",
            },
            method="GET",
        )

        with self.opener(
            request,
            timeout=self.timeout,
        ) as response:
            return json.load(response)

    def optional_get(self, endpoint: str) -> Any:
        try:
            return self.get(endpoint)
        except HTTPError as exc:
            if exc.code in {400, 404}:
                return {}
            raise


class CargoResolver:
    """Build a bounded JSON-safe view of recent application imports."""

    def __init__(
        self,
        *,
        sonarr_client: ServarrClient,
        radarr_client: ServarrClient,
        clock: Callable[[], float],
        window_seconds: int = 86400,
        history_limit: int = 250,
    ) -> None:
        self.sonarr_client = sonarr_client
        self.radarr_client = radarr_client
        self.clock = clock
        self.window_seconds = max(1, int(window_seconds))
        self.history_limit = max(1, int(history_limit))

    @staticmethod
    def _parse_date(value: Any) -> float | None:
        text = str(value or "").strip()

        if not text:
            return None

        try:
            parsed = datetime.fromisoformat(
                text.replace("Z", "+00:00")
            )
        except ValueError:
            return None

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)

        return parsed.timestamp()

    @staticmethod
    def _history_file_id(event: dict[str, Any]) -> int | None:
        value = (event.get("data") or {}).get("fileId")

        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _host_path(
        config: ServarrConfig,
        media_path: Any,
    ) -> Path | None:
        text = str(media_path or "")

        if not text.startswith(config.media_prefix):
            return None

        suffix = text[len(config.media_prefix):].lstrip("/")

        return config.host_prefix / suffix

    @staticmethod
    def _file_state(path: Path | None) -> tuple[bool, int | None]:
        if path is None or not path.is_file():
            return False, None

        try:
            return True, path.stat().st_size
        except OSError:
            return False, None

    @staticmethod
    def _history_size(event: dict[str, Any]) -> int | None:
        return CargoResolver._safe_int(
            (event.get("data") or {}).get("size")
        )

    def _history(
        self,
        client: ServarrClient,
    ) -> list[dict[str, Any]]:
        payload = client.get(
            "/api/v3/history",
            {
                "page": 1,
                "pageSize": self.history_limit,
                "sortKey": "date",
                "sortDirection": "descending",
            },
        )

        if not isinstance(payload, dict):
            return []

        records = payload.get("records")

        if not isinstance(records, list):
            return []

        cutoff = self.clock() - self.window_seconds
        result = []

        for record in records:
            if not isinstance(record, dict):
                continue

            if record.get("eventType") != "downloadFolderImported":
                continue

            timestamp = self._parse_date(record.get("date"))

            if timestamp is None or timestamp < cutoff:
                continue

            item = dict(record)
            item["_timestamp"] = timestamp
            result.append(item)

        return result

    def _resolve_sonarr(self) -> list[dict[str, Any]]:
        client = self.sonarr_client
        config = client.config

        series_payload = client.get("/api/v3/series")

        series_by_id = {
            item.get("id"): item
            for item in series_payload
            if isinstance(item, dict)
        }

        cargo = []

        for event in self._history(client):
            series_id = event.get("seriesId")
            episode_id = event.get("episodeId")
            history_file_id = self._history_file_id(event)

            series = series_by_id.get(series_id) or {}

            episode = (
                client.optional_get(
                    f"/api/v3/episode/{episode_id}"
                )
                if episode_id is not None
                else {}
            )

            file_obj = {}
            current_file_id = history_file_id
            resolution = "history-file-id"

            if history_file_id is not None:
                file_obj = client.optional_get(
                    f"/api/v3/episodefile/{history_file_id}"
                )

            if not file_obj:
                fallback_id = self._safe_int(
                    episode.get("episodeFileId")
                )

                if fallback_id is not None:
                    candidate = client.optional_get(
                        f"/api/v3/episodefile/{fallback_id}"
                    )

                    if candidate:
                        file_obj = candidate
                        current_file_id = fallback_id
                        resolution = "episode-current-file-id"

            media_path = None

            relative = file_obj.get("relativePath")
            series_path = series.get("path")

            if relative and series_path:
                media_path = str(
                    Path(str(series_path)) / str(relative)
                )

            current_path = self._host_path(
                config,
                media_path,
            )

            exists, disk_size = self._file_state(current_path)

            season = episode.get("seasonNumber")
            number = episode.get("episodeNumber")
            title = str(
                episode.get("title") or "Unknown Episode"
            )

            if season is not None and number is not None:
                detail = (
                    f"{season}x{int(number):02d} - {title}"
                )
            else:
                detail = title

            data = event.get("data") or {}
            original_path = data.get("importedPath")
            original_host = self._host_path(
                config,
                original_path,
            )

            moved = bool(
                original_host
                and current_path
                and original_host != current_path
            )

            cargo.append(
                {
                    "source": "sonarr",
                    "kind": "tv",
                    "history_id": event.get("id"),
                    "media_id": episode_id,
                    "parent_id": series_id,
                    "history_file_id": history_file_id,
                    "current_file_id": current_file_id,
                    "resolution": (
                        resolution
                        if file_obj
                        else "unresolved"
                    ),
                    "imported_at": event["_timestamp"],
                    "title": (
                        series.get("title")
                        or "Unknown Series"
                    ),
                    "detail": detail,
                    "current_path": (
                        str(current_path)
                        if current_path
                        else None
                    ),
                    "original_path": original_path,
                    "exists": exists,
                    "moved_since_import": moved,
                    "size_bytes": (
                        disk_size
                        if disk_size is not None
                        else self._history_size(event)
                    ),
                }
            )

        return cargo

    def _resolve_radarr(self) -> list[dict[str, Any]]:
        client = self.radarr_client
        config = client.config

        movie_payload = client.get("/api/v3/movie")

        movies_by_id = {
            item.get("id"): item
            for item in movie_payload
            if isinstance(item, dict)
        }

        cargo = []

        for event in self._history(client):
            movie_id = event.get("movieId")
            history_file_id = self._history_file_id(event)

            movie = movies_by_id.get(movie_id) or {}

            file_obj = {}
            current_file_id = history_file_id
            resolution = "history-file-id"

            if history_file_id is not None:
                file_obj = client.optional_get(
                    f"/api/v3/moviefile/{history_file_id}"
                )

            if not file_obj:
                fallback_id = self._safe_int(
                    movie.get("movieFileId")
                )

                if fallback_id is not None:
                    candidate = client.optional_get(
                        f"/api/v3/moviefile/{fallback_id}"
                    )

                    if candidate:
                        file_obj = candidate
                        current_file_id = fallback_id
                        resolution = "movie-current-file-id"

            media_path = None

            relative = file_obj.get("relativePath")
            movie_path = movie.get("path")

            if relative and movie_path:
                media_path = str(
                    Path(str(movie_path)) / str(relative)
                )

            current_path = self._host_path(
                config,
                media_path,
            )

            exists, disk_size = self._file_state(current_path)

            data = event.get("data") or {}
            original_path = data.get("importedPath")
            original_host = self._host_path(
                config,
                original_path,
            )

            moved = bool(
                original_host
                and current_path
                and original_host != current_path
            )

            title = str(
                movie.get("title") or "Unknown Movie"
            )
            year = movie.get("year")

            if year:
                title = f"{title} ({year})"

            cargo.append(
                {
                    "source": "radarr",
                    "kind": "movie",
                    "history_id": event.get("id"),
                    "media_id": movie_id,
                    "parent_id": None,
                    "history_file_id": history_file_id,
                    "current_file_id": current_file_id,
                    "resolution": (
                        resolution
                        if file_obj
                        else "unresolved"
                    ),
                    "imported_at": event["_timestamp"],
                    "title": title,
                    "detail": (
                        current_path.name
                        if current_path
                        else "Unknown file"
                    ),
                    "current_path": (
                        str(current_path)
                        if current_path
                        else None
                    ),
                    "original_path": original_path,
                    "exists": exists,
                    "moved_since_import": moved,
                    "size_bytes": (
                        disk_size
                        if disk_size is not None
                        else self._history_size(event)
                    ),
                }
            )

        return cargo

    def snapshot(self) -> dict[str, Any]:
        """Return the current bounded Cargo Bay discovery payload."""

        try:
            tv = self._resolve_sonarr()
        except (
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
            HTTPError,
        ):
            tv = []

        try:
            movies = self._resolve_radarr()
        except (
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
            HTTPError,
        ):
            movies = []

        items = tv + movies
        items.sort(
            key=lambda item: float(
                item.get("imported_at") or 0.0
            ),
            reverse=True,
        )

        unresolved = sum(
            not bool(item.get("exists"))
            for item in items
        )
        moved = sum(
            bool(item.get("moved_since_import"))
            for item in items
        )
        total_bytes = sum(
            int(item.get("size_bytes") or 0)
            for item in items
        )

        if unresolved:
            state = "REVIEW"
        elif items:
            state = "NOMINAL"
        else:
            state = "CLEAR"

        return {
            "schema_version": 1,
            "read_only": True,
            "state": state,
            "window_seconds": self.window_seconds,
            "summary": {
                "total": len(items),
                "tv": len(tv),
                "movies": len(movies),
                "resolved": len(items) - unresolved,
                "unresolved": unresolved,
                "moved_since_import": moved,
                "total_bytes": total_bytes,
            },
            "backup": {
                "tracking": False,
                "state": "NOT_TRACKED",
            },
            "groups": {
                "tv": tv,
                "movies": movies,
            },
        }
