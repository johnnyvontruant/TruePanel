import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from truepanel.cargo.backlog import (
    LOADMASTER_BACKLOG_KIND,
    LoadmasterBacklogError,
    empty_backlog,
    load_backlog,
    reconcile_backlog,
    write_backlog_atomic,
)


NOW = datetime(
    2026,
    10,
    3,
    20,
    0,
    tzinfo=UTC,
)


def cargo_item(
    *,
    path="/mnt/HDDs/Movies/Movies E-I/Heat (1995)/Heat (1995).mkv",
    size=100,
    imported_at=1_796_502_000.0,
):
    return {
        "title": "Heat",
        "detail": "Heat (1995)",
        "source": "radarr",
        "current_path": path,
        "size_bytes": size,
        "imported_at": imported_at,
    }


def manifest(
    *,
    path="/mnt/HDDs/Movies/Movies E-I/Heat (1995)/Heat (1995).mkv",
    size=100,
    backed_up_at="2026-10-03T21:00:00+00:00",
):
    return {
        "schema_version": 1,
        "kind": "truepanel.cargo_backup_manifest",
        "created_at": backed_up_at,
        "source": "test",
        "items": [
            {
                "path": path,
                "size_bytes": size,
                "backed_up_at": backed_up_at,
            }
        ],
    }


def test_pending_item_survives_empty_recent_window():
    first, report = reconcile_backlog(
        previous=empty_backlog(
            updated_at=NOW
        ),
        cargo_items=[cargo_item()],
        manifest=None,
        observed_at=NOW,
    )

    assert report["pending_items"] == 1

    later, report = reconcile_backlog(
        previous=first,
        cargo_items=[],
        manifest=None,
        observed_at=datetime(
            2026,
            10,
            5,
            20,
            0,
            tzinfo=UTC,
        ),
    )

    assert report["observed_items"] == 0
    assert report["pending_items"] == 1
    assert len(later["items"]) == 1
    assert (
        later["items"][0]["current_path"]
        == cargo_item()["current_path"]
    )


def test_verified_manifest_clears_old_backlog_item():
    first, _ = reconcile_backlog(
        previous=None,
        cargo_items=[cargo_item()],
        manifest=None,
        observed_at=NOW,
    )

    cleared, report = reconcile_backlog(
        previous=first,
        cargo_items=[],
        manifest=manifest(),
        observed_at=datetime(
            2026,
            10,
            3,
            22,
            0,
            tzinfo=UTC,
        ),
    )

    assert report["verified"] == 1
    assert report["pending_items"] == 0
    assert cleared["items"] == []


def test_stale_manifest_does_not_clear_backlog():
    imported = datetime(
        2026,
        10,
        3,
        19,
        0,
        tzinfo=UTC,
    ).timestamp()

    payload, _ = reconcile_backlog(
        previous=None,
        cargo_items=[
            cargo_item(
                imported_at=imported
            )
        ],
        manifest=manifest(
            backed_up_at=(
                "2026-10-03T18:59:59+00:00"
            )
        ),
        observed_at=NOW,
    )

    assert len(payload["items"]) == 1

    _, report = reconcile_backlog(
        previous=payload,
        cargo_items=[],
        manifest=manifest(
            backed_up_at=(
                "2026-10-03T18:59:59+00:00"
            )
        ),
        observed_at=NOW,
    )

    assert report["stale"] == 1
    assert report["pending_items"] == 1


def test_size_change_requires_new_backup_evidence():
    original, _ = reconcile_backlog(
        previous=None,
        cargo_items=[
            cargo_item(
                size=100,
                imported_at=datetime(
                    2026,
                    10,
                    3,
                    18,
                    0,
                    tzinfo=UTC,
                ).timestamp(),
            )
        ],
        manifest=None,
        observed_at=datetime(
            2026,
            10,
            3,
            18,
            5,
            tzinfo=UTC,
        ),
    )

    changed_at = datetime(
        2026,
        10,
        3,
        20,
        30,
        tzinfo=UTC,
    )

    changed, _ = reconcile_backlog(
        previous=original,
        cargo_items=[
            cargo_item(
                size=200,
                imported_at=changed_at.timestamp(),
            )
        ],
        manifest=manifest(
            size=200,
            backed_up_at=(
                "2026-10-03T20:00:00+00:00"
            ),
        ),
        observed_at=datetime(
            2026,
            10,
            3,
            20,
            31,
            tzinfo=UTC,
        ),
    )

    assert len(changed["items"]) == 1

    cleared, report = reconcile_backlog(
        previous=changed,
        cargo_items=[],
        manifest=manifest(
            size=200,
            backed_up_at=(
                "2026-10-03T21:00:00+00:00"
            ),
        ),
        observed_at=datetime(
            2026,
            10,
            3,
            21,
            1,
            tzinfo=UTC,
        ),
    )

    assert report["verified"] == 1
    assert cleared["items"] == []


def test_size_mismatch_remains_pending():
    payload, report = reconcile_backlog(
        previous=None,
        cargo_items=[cargo_item()],
        manifest=manifest(size=99),
        observed_at=NOW,
    )

    assert len(payload["items"]) == 1
    assert report["mismatch"] == 1
    assert report["pending_items"] == 1


def test_invalid_relative_cargo_path_fails_closed():
    with pytest.raises(
        LoadmasterBacklogError,
        match="absolute",
    ):
        reconcile_backlog(
            previous=None,
            cargo_items=[
                cargo_item(
                    path="Movies/Heat.mkv"
                )
            ],
            manifest=None,
            observed_at=NOW,
        )


def test_atomic_roundtrip(tmp_path):
    output = tmp_path / "pending-cargo.json"

    payload, _ = reconcile_backlog(
        previous=None,
        cargo_items=[cargo_item()],
        manifest=None,
        observed_at=NOW,
    )

    write_backlog_atomic(
        output,
        payload,
    )

    loaded = load_backlog(
        output
    )

    assert loaded == payload
    assert (
        loaded["kind"]
        == LOADMASTER_BACKLOG_KIND
    )


def test_atomic_writer_rejects_relative_output():
    with pytest.raises(
        LoadmasterBacklogError,
        match="absolute",
    ):
        write_backlog_atomic(
            Path("pending-cargo.json"),
            empty_backlog(
                updated_at=NOW
            ),
        )


def test_duplicate_paths_are_rejected(tmp_path):
    path = tmp_path / "pending-cargo.json"
    item = {
        "title": "Heat",
        "detail": None,
        "source": "radarr",
        "current_path": cargo_item()[
            "current_path"
        ],
        "size_bytes": 100,
        "source_imported_at": None,
        "first_seen_at": NOW.isoformat(),
        "last_seen_at": NOW.isoformat(),
        "required_after": NOW.isoformat(),
    }

    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": LOADMASTER_BACKLOG_KIND,
                "updated_at": NOW.isoformat(),
                "items": [item, item],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        LoadmasterBacklogError,
        match="duplicate",
    ):
        load_backlog(path)
