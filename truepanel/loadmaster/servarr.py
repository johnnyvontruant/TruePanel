"""Keep a log of what Sonarr and Radarr import, upgrade and delete.

Loadmaster does not need this log to decide what to copy (the drive plan
compares folders directly), but it is how TruePanel answers "what came in,
and which drive does it belong to?" while drives sit in a drawer. History is
read through the existing read-only Servarr client; only new records since the
last poll are logged.
"""

from __future__ import annotations

import logging
from pathlib import Path

from truepanel.cargo.resolver import ServarrClient, ServarrConfig

from .config import Settings
from .state import StateStore

LOGGER = logging.getLogger(__name__)

EVENTS = {
    "downloadFolderImported": "imported",
    "episodeFileDeleted": "deleted",
    "movieFileDeleted": "deleted",
    "episodeFileRenamed": "renamed",
    "movieFileRenamed": "renamed",
}
PAGE_SIZE = 100
# Pages read back per poll before giving up on reaching the cursor. 20 pages is
# 2,000 history records: far more than a five-minute poll ever sees, but enough
# to catch up after TruePanel was down for a day while a whole series came in.
MAX_PAGES = 20


def host_path(config: ServarrConfig, path: str) -> Path | None:
    if not path:
        return None
    prefix = config.media_prefix.rstrip("/")
    if prefix and (path == prefix or path.startswith(prefix + "/")):
        return config.host_prefix / path[len(prefix) :].lstrip("/")
    return Path(path) if path.startswith("/") else None


def poll(
    settings: Settings,
    store: StateStore,
    *,
    client_factory=ServarrClient,
) -> dict[str, str]:
    """Log new history records. Returns per-app status ("ok" or an error)."""

    status: dict[str, str] = {}
    for config in (settings.sonarr, settings.radarr):
        if config is None:
            continue
        try:
            count = _poll_one(config, settings, store, client_factory(config))
            status[config.name] = f"ok ({count} new)" if count else "ok"
        except Exception as error:  # noqa: BLE001 - surface, never crash the loop
            LOGGER.warning("Loadmaster %s poll failed: %s", config.name, error)
            status[config.name] = f"unreachable: {error}"
    return status


def _record_id(record: dict) -> int:
    try:
        return int(record.get("id") or 0)
    except (TypeError, ValueError):
        return 0


def _fetch_page(client, page: int) -> list[dict]:
    payload = client.get(
        "/api/v3/history",
        {
            "page": page,
            "pageSize": PAGE_SIZE,
            "sortKey": "date",
            "sortDirection": "descending",
        },
    )
    return [r for r in (payload or {}).get("records") or [] if isinstance(r, dict)]


def _poll_one(
    config: ServarrConfig, settings: Settings, store: StateStore, client
) -> int:
    cursor_name = f"{config.name}_history_id"
    last_id = store.load_cursor(cursor_name)
    records = _fetch_page(client, 1)
    newest = max((_record_id(r) for r in records), default=0)

    if last_id is None:
        # First start: remember where history is, don't replay the past.
        store.save_cursor(cursor_name, newest)
        return 0
    last_id = int(last_id)

    # History is newest first. Keep reading older pages until one reaches the
    # cursor, so a burst of more than one page between polls (a restart, an
    # outage, a big season pack) is logged in full instead of silently cut.
    def reaches_cursor(batch: list[dict]) -> bool:
        return (
            len(batch) < PAGE_SIZE  # last page of history (or empty)
            or any(_record_id(r) <= last_id for r in batch)
        )

    page = 1
    reached = reaches_cursor(records)
    while not reached and page < MAX_PAGES:
        page += 1
        older = _fetch_page(client, page)
        records.extend(older)
        reached = reaches_cursor(older)

    fresh = {_record_id(r): r for r in records if _record_id(r) > last_id}
    fresh = list(fresh.values())
    if not reached:
        oldest = min((_record_id(r) for r in fresh), default=newest)
        LOGGER.warning(
            "Loadmaster %s history: more than %d new records; ids %d-%d not logged",
            config.name,
            MAX_PAGES * PAGE_SIZE,
            last_id + 1,
            oldest - 1,
        )
        store.log(
            "history_gap",
            app=config.name,
            detail=f"history records {last_id + 1}-{oldest - 1} were not logged "
            f"(more than {MAX_PAGES * PAGE_SIZE} arrived between polls)",
        )
    for record in sorted(fresh, key=_record_id):
        event = EVENTS.get(str(record.get("eventType")))
        if event is None:
            continue
        data = record.get("data") if isinstance(record.get("data"), dict) else {}
        path = host_path(config, str(data.get("importedPath") or ""))
        drive = settings.drive_for_path(path) if path else None
        store.log(
            event,
            app=config.name,
            title=str(record.get("sourceTitle") or ""),
            path=str(path) if path else None,
            drive=drive.name if drive else None,
            detail=str(data.get("reason") or "") or None,
        )
    if newest > last_id:
        store.save_cursor(cursor_name, newest)
    return len(fresh)


__all__ = ["host_path", "poll"]
