"""Read-only Plex activity experiment.

The provider intentionally depends only on the Python standard library.  It
normalizes Plex session XML and never exposes the authentication token through
returned state, errors, or persisted payloads.
"""

from __future__ import annotations

from collections.abc import Callable
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from .model import ActivityItem, ActivityState

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


def parse_plex_sessions(payload: bytes | str) -> tuple[ActivityItem, ...]:
    """Normalize Plex ``/status/sessions`` XML into safe activity items."""
    root = ElementTree.fromstring(payload)
    items: list[ActivityItem] = []
    for node in root:
        if node.tag not in {"Video", "Track", "Photo"}:
            continue

        title = node.get("title") or node.get("grandparentTitle") or "Untitled"
        series = node.get("grandparentTitle")
        episode = node.get("parentTitle")
        subtitle = " · ".join(part for part in (series, episode) if part)
        if subtitle == title:
            subtitle = ""

        items.append(
            ActivityItem(
                source="plex",
                state=_state(node),
                title=title,
                subtitle=subtitle or None,
                progress=_progress(node.get("viewOffset"), node.get("duration")),
                kind=node.get("type") or node.tag.lower(),
            )
        )
    return tuple(items)


class PlexActivityProvider:
    """Fetch current Plex sessions without coupling Plex to TruePanel UI code."""

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
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._fetcher = fetcher

    def snapshot(self) -> tuple[ActivityItem, ...]:
        """Return current sessions. Network failures remain integration-local."""
        request = Request(
            f"{self._base_url}/status/sessions",
            headers={"X-Plex-Token": self._token, "Accept": "application/xml"},
        )
        return parse_plex_sessions(self._fetcher(request, self._timeout))
