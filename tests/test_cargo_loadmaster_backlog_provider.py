import json
from datetime import UTC, datetime

from truepanel.cargo import (
    CachedCargoProvider,
    provider_from_config,
    reconcile_backlog,
    write_backlog_atomic,
)


class Resolver:
    def __init__(self, payload):
        self.payload = payload

    def snapshot(self):
        return self.payload


def empty_resolver_payload():
    return {
        "schema_version": 1,
        "read_only": True,
        "state": "CLEAR",
        "summary": {
            "total": 0,
            "tv": 0,
            "movies": 0,
            "resolved": 0,
            "unresolved": 0,
            "moved_since_import": 0,
            "total_bytes": 0,
        },
        "groups": {
            "tv": [],
            "movies": [],
        },
    }


def write_registry(tmp_path):
    path = tmp_path / "cartridges.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": (
                    "truepanel.loadmaster_cartridge_registry"
                ),
                "cartridges": [
                    {
                        "id": "movies-e-i",
                        "label": "Movies E-I",
                        "uuid": "ABCD-1234",
                        "role": "movies",
                        "source_prefix": (
                            "/mnt/HDDs/Movies/Movies E-I"
                        ),
                        "usb_relative_path": "Movies E-I",
                        "allow_ingest": True,
                        "allow_backup": True,
                        "delete_policy": "never",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def write_pending_backlog(tmp_path):
    path = tmp_path / "pending-cargo.json"
    item = {
        "title": "Heat",
        "detail": "Heat (1995)",
        "source": "radarr",
        "current_path": (
            "/mnt/HDDs/Movies/Movies E-I/"
            "Heat (1995)/Heat (1995).mkv"
        ),
        "size_bytes": 100,
        "imported_at": datetime(
            2026,
            10,
            3,
            18,
            0,
            tzinfo=UTC,
        ).timestamp(),
    }

    payload, _ = reconcile_backlog(
        previous=None,
        cargo_items=[item],
        manifest=None,
        observed_at=datetime(
            2026,
            10,
            3,
            18,
            1,
            tzinfo=UTC,
        ),
    )

    write_backlog_atomic(
        path,
        payload,
    )
    return path, item


def test_provider_uses_backlog_after_recent_window_is_empty(
    tmp_path,
):
    registry = write_registry(tmp_path)
    backlog, _ = write_pending_backlog(
        tmp_path
    )

    provider = CachedCargoProvider(
        Resolver(
            empty_resolver_payload()
        ),
        cache_seconds=0,
        loadmaster_enabled=True,
        cartridge_registry_path=registry,
        loadmaster_backlog_path=backlog,
    )

    result = provider.snapshot()
    loadmaster = result["loadmaster"]

    assert loadmaster["state"] == "AWAITING"
    assert loadmaster["pending_items"] == 1
    assert (
        loadmaster["next_cartridge"]["label"]
        == "Movies E-I"
    )
    assert (
        loadmaster["backlog"]["tracking"]
        is True
    )
    assert (
        loadmaster["backlog"]["pending_items"]
        == 1
    )


def test_provider_fail_closes_invalid_backlog(
    tmp_path,
):
    registry = write_registry(tmp_path)
    backlog = tmp_path / "pending-cargo.json"
    backlog.write_text(
        '{"schema_version": 999}',
        encoding="utf-8",
    )

    provider = CachedCargoProvider(
        Resolver(
            empty_resolver_payload()
        ),
        cache_seconds=0,
        loadmaster_enabled=True,
        cartridge_registry_path=registry,
        loadmaster_backlog_path=backlog,
    )

    loadmaster = provider.snapshot()[
        "loadmaster"
    ]

    assert loadmaster["state"] == "INVALID"
    assert (
        "backlog"
        in loadmaster["invalid_reason"].lower()
    )


def test_provider_correlates_backup_evidence_for_backlog(
    tmp_path,
):
    registry = write_registry(tmp_path)
    backlog, item = write_pending_backlog(
        tmp_path
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
                    "2026-10-03T19:00:00+00:00"
                ),
                "source": "loadmaster-test",
                "items": [
                    {
                        "path": item[
                            "current_path"
                        ],
                        "size_bytes": 100,
                        "backed_up_at": (
                            "2026-10-03T19:00:00+00:00"
                        ),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    provider = CachedCargoProvider(
        Resolver(
            empty_resolver_payload()
        ),
        cache_seconds=0,
        backup_manifest_path=manifest,
        loadmaster_enabled=True,
        cartridge_registry_path=registry,
        loadmaster_backlog_path=backlog,
    )

    loadmaster = provider.snapshot()[
        "loadmaster"
    ]

    assert loadmaster["state"] == "CLEAR"
    assert loadmaster["pending_items"] == 0
    assert (
        loadmaster["cartridges"][0][
            "verified_items"
        ]
        == 1
    )


def test_config_accepts_loadmaster_backlog_path():
    provider = provider_from_config(
        {
            "mission_control": {
                "cargo_bay": {
                    "enabled": True,
                    "sonarr": {
                        "url": "http://sonarr:8989",
                        "config_path": (
                            "/config/sonarr.xml"
                        ),
                        "host_prefix": (
                            "/tank/shows"
                        ),
                    },
                    "radarr": {
                        "url": "http://radarr:7878",
                        "config_path": (
                            "/config/radarr.xml"
                        ),
                        "host_prefix": (
                            "/tank/movies"
                        ),
                    },
                    "loadmaster": {
                        "enabled": True,
                        "cartridge_registry_path": (
                            "/state/cartridges.json"
                        ),
                        "backlog_path": (
                            "/state/pending-cargo.json"
                        ),
                    },
                }
            }
        }
    )

    assert provider is not None
    assert (
        str(
            provider.loadmaster_backlog_path
        )
        == "/state/pending-cargo.json"
    )
