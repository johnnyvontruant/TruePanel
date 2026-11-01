"""Read-only Plex activity provider for Project OBSERVATORY."""

from __future__ import annotations

from collections.abc import Callable
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from .model import (
    ActivityIntensity,
    ActivityObservation,
    ActivityProviderStatus,
    ActivitySnapshot,
    ActivityState,
)

Fetcher = Callable[[Request, float], bytes]


def _default_fetcher(request: Request, timeout: float) -> bytes:
    with urlopen(request, timeout=timeout) as response:  # noqa: S310
        return response.read()


def _progress(view_offset: str | None, duration: str | None) -> float | None:
    if view_offset is None or duration is None:
        return None
    try:
        total = int(duration)
        current = int(view_offset)
    except ValueError:
        return None
    if total <= 0:
        return None
    return min(1.0, max(0.0, current / total))


def _state(node: ElementTree.Element) -> ActivityState:
    player = node.find("Player")
    raw = player.get("state", "") if player is not None else ""
    if raw == "playing":
        return ActivityState.PLAYING
    if raw == "paused":
        return ActivityState.PAUSED
    return ActivityState.UNKNOWN


def _intensity(state: ActivityState) -> ActivityIntensity:
    if state is ActivityState.PLAYING:
        return ActivityIntensity.MODERATE
    if state is ActivityState.PAUSED:
        return ActivityIntensity.LOW
    return ActivityIntensity.UNKNOWN


def parse_plex_sessions(payload: bytes | str) -> tuple[ActivityObservation, ...]:
    """Normalize Plex ``/status/sessions`` XML without leaking session identity."""

    root = ElementTree.fromstring(payload)
    observations: list[ActivityObservation] = []
    for node in root:
        if node.tag not in {"Video", "Track", "Photo"}:
            continue

        title = node.get("title") or node.get("grandparentTitle") or "Untitled"
        series = node.get("grandparentTitle")
        episode = node.get("parentTitle")
        subtitle = " · ".join(part for part in (series, episode) if part)
        if subtitle == title:
            subtitle = ""

        state = _state(node)
        observations.append(
            ActivityObservation(
                source="plex",
                kind=node.get("type") or node.tag.lower(),
                state=state,
                title=title,
                subtitle=subtitle or None,
                progress=_progress(node.get("viewOffset"), node.get("duration")),
                confidence=1.0,
                intensity=_intensity(state),
                evidence=("plex.status.sessions",),
            )
        )

    return tuple(observations)


class PlexActivityProvider:
    """Fetch Plex sessions without coupling credentials or XML to TruePanel UI."""

    source = "plex"

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = 2.0,
        fetcher: Fetcher = _default_fetcher,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("Plex base_url must use http or https")
        if not token:
            raise ValueError("Plex token must not be empty")
        if timeout <= 0:
            raise ValueError("Plex timeout must be positive")
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = float(timeout)
        self._fetcher = fetcher

    def snapshot(self) -> ActivitySnapshot:
        """Return normalized activity and fail closed when Plex is unavailable."""

        request = Request(
            f"{self._base_url}/status/sessions",
            headers={"X-Plex-Token": self._token, "Accept": "application/xml"},
        )
        try:
            observations = parse_plex_sessions(
                self._fetcher(request, self._timeout)
            )
        except Exception:
            # Provider failures must never break TruePanel core monitoring or
            # expose raw exception text that could contain credentials.
            return ActivitySnapshot(
                source=self.source,
                status=ActivityProviderStatus.UNAVAILABLE,
            )

        return ActivitySnapshot(
            source=self.source,
            status=ActivityProviderStatus.AVAILABLE,
            observations=observations,
        )


__all__ = ["PlexActivityProvider", "parse_plex_sessions"]
