import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from truepanel.cargo.backlog import (
    empty_backlog,
    load_backlog,
    write_backlog_atomic,
)
from truepanel.cargo.backlog_observer import (
    LoadmasterObserverError,
    observe_once,
)


BASELINE = datetime(
    2026,
    10,
    4,
    2,
    36,
    7,
    tzinfo=UTC,
)

OBSERVED = datetime(
    2026,
    10,
    4,
    3,
    5,
    tzinfo=UTC,
)


class Resolver:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def snapshot(self):
        self.calls += 1
        return self.payload


class Provider:
    def __init__(
        self,
        *,
        backlog_path,
        payload,
        manifest_path=None,
    ):
        self.loadmaster_backlog_path = (
            backlog_path
        )
        self.backup_manifest_path = (
            manifest_path
        )
        self.resolver = Resolver(payload)


def cargo_payload(
    *,
    imported_at,
    size=100,
):
    return {
        "schema_version": 1,
        "read_only": True,
        "state": "NOMINAL",
        "groups": {
            "tv": [],
            "movies": [
                {
                    "title": "Heat",
                    "detail": "Heat (1995)",
                    "source": "radarr",
                    "current_path": (
                        "/mnt/HDDs/Movies/Movies E-I/"
                        "Heat (1995)/Heat (1995).mkv"
                    ),
                    "size_bytes": size,
                    "imported_at": imported_at,
                }
            ],
        },
    }


def prepare_backlog(tmp_path):
    path = tmp_path / "pending-cargo.json"
    write_backlog_atomic(
        path,
        empty_backlog(
            updated_at=BASELINE,
            observe_after=BASELINE,
        ),
    )
    return path


def test_observer_persists_post_baseline_cargo(
    tmp_path,
):
    backlog = prepare_backlog(
        tmp_path
    )
    provider = Provider(
        backlog_path=backlog,
        payload=cargo_payload(
            imported_at=datetime(
                2026,
                10,
                4,
                3,
                0,
                tzinfo=UTC,
            ).timestamp(),
        ),
    )

    report = observe_once(
        provider,
        observed_at=OBSERVED,
    )

    assert provider.resolver.calls == 1
    assert report["pending_items"] == 1
    assert report["wrote_backlog"] is True

    persisted = load_backlog(
        backlog
    )

    assert len(persisted["items"]) == 1
    assert (
        persisted["items"][0]["title"]
        == "Heat"
    )


def test_observer_ignores_pre_baseline_history(
    tmp_path,
):
    backlog = prepare_backlog(
        tmp_path
    )
    provider = Provider(
        backlog_path=backlog,
        payload=cargo_payload(
            imported_at=datetime(
                2026,
                10,
                4,
                2,
                0,
                tzinfo=UTC,
            ).timestamp(),
        ),
    )

    report = observe_once(
        provider,
        observed_at=OBSERVED,
    )

    assert report["pending_items"] == 0
    assert (
        report["ignored_before_baseline"]
        == 1
    )
    assert load_backlog(
        backlog
    )["items"] == []


def test_observer_dry_run_does_not_change_backlog(
    tmp_path,
):
    backlog = prepare_backlog(
        tmp_path
    )
    before = backlog.read_text(
        encoding="utf-8"
    )

    provider = Provider(
        backlog_path=backlog,
        payload=cargo_payload(
            imported_at=datetime(
                2026,
                10,
                4,
                3,
                0,
                tzinfo=UTC,
            ).timestamp(),
        ),
    )

    report = observe_once(
        provider,
        observed_at=OBSERVED,
        dry_run=True,
    )

    assert report["pending_items"] == 1
    assert report["wrote_backlog"] is False
    assert (
        backlog.read_text(
            encoding="utf-8"
        )
        == before
    )


def test_observer_requires_existing_baseline(
    tmp_path,
):
    provider = Provider(
        backlog_path=(
            tmp_path
            / "missing.json"
        ),
        payload=cargo_payload(
            imported_at=OBSERVED.timestamp(),
        ),
    )

    with pytest.raises(
        LoadmasterObserverError,
        match="missing Loadmaster backlog",
    ):
        observe_once(
            provider,
            observed_at=OBSERVED,
        )


def test_observer_verified_manifest_clears_pending(
    tmp_path,
):
    backlog = prepare_backlog(
        tmp_path
    )
    imported = datetime(
        2026,
        10,
        4,
        3,
        0,
        tzinfo=UTC,
    )

    first = Provider(
        backlog_path=backlog,
        payload=cargo_payload(
            imported_at=imported.timestamp(),
        ),
    )

    observe_once(
        first,
        observed_at=OBSERVED,
    )

    manifest = tmp_path / "backup.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": (
                    "truepanel.cargo_backup_manifest"
                ),
                "created_at": (
                    "2026-10-04T04:00:00+00:00"
                ),
                "source": "loadmaster-test",
                "items": [
                    {
                        "path": (
                            "/mnt/HDDs/Movies/Movies E-I/"
                            "Heat (1995)/Heat (1995).mkv"
                        ),
                        "size_bytes": 100,
                        "backed_up_at": (
                            "2026-10-04T04:00:00+00:00"
                        ),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    second = Provider(
        backlog_path=backlog,
        manifest_path=manifest,
        payload={
            "schema_version": 1,
            "groups": {
                "tv": [],
                "movies": [],
            },
        },
    )

    report = observe_once(
        second,
        observed_at=datetime(
            2026,
            10,
            4,
            4,
            1,
            tzinfo=UTC,
        ),
    )

    assert report["verified"] == 1
    assert report["pending_items"] == 0
    assert load_backlog(
        backlog
    )["items"] == []


def test_observer_rejects_missing_backlog_path():
    provider = Provider(
        backlog_path=None,
        payload={
            "groups": {
                "tv": [],
                "movies": [],
            },
        },
    )

    with pytest.raises(
        LoadmasterObserverError,
        match="backlog_path",
    ):
        observe_once(provider)
