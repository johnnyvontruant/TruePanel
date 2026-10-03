import json

from truepanel.cargo import CachedCargoProvider
from truepanel.cargo.cartridges import (
    LOADMASTER_REGISTRY_KIND,
)


class Resolver:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def snapshot(self):
        self.calls += 1
        return self.payload


def payload(path):
    return {
        "schema_version": 1,
        "read_only": True,
        "state": "NOMINAL",
        "summary": {
            "total": 1,
            "tv": 0,
            "movies": 1,
            "resolved": 1,
            "unresolved": 0,
            "moved_since_import": 0,
            "total_bytes": 100,
        },
        "groups": {
            "tv": [],
            "movies": [
                {
                    "title": "Heat",
                    "detail": "Heat (1995)",
                    "source": "radarr",
                    "current_path": path,
                    "size_bytes": 100,
                    "imported_at": 1000.0,
                }
            ],
        },
    }


def registry_payload():
    return {
        "schema_version": 1,
        "kind": LOADMASTER_REGISTRY_KIND,
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


def test_provider_marks_loadmaster_disabled_without_registry():
    media_path = (
        "/mnt/HDDs/Movies/Movies E-I/"
        "Heat (1995)/Heat (1995).mkv"
    )

    provider = CachedCargoProvider(
        Resolver(payload(media_path)),
        cache_seconds=0,
    )

    result = provider.snapshot()

    assert result["loadmaster"]["enabled"] is False
    assert result["loadmaster"]["state"] == "DISABLED"


def test_provider_attaches_pending_cartridge_summary(
    tmp_path,
):
    media_path = (
        "/mnt/HDDs/Movies/Movies E-I/"
        "Heat (1995)/Heat (1995).mkv"
    )

    registry = tmp_path / "cartridges.json"
    registry.write_text(
        json.dumps(registry_payload()),
        encoding="utf-8",
    )

    provider = CachedCargoProvider(
        Resolver(payload(media_path)),
        cache_seconds=0,
        cartridge_registry_path=registry,
    )

    result = provider.snapshot()
    loadmaster = result["loadmaster"]

    assert loadmaster["enabled"] is True
    assert loadmaster["state"] == "AWAITING"
    assert loadmaster["pending_items"] == 1
    assert loadmaster["pending_bytes"] == 100
    assert (
        loadmaster["next_cartridge"]["label"]
        == "Movies E-I"
    )


def test_provider_fail_closes_invalid_registry(
    tmp_path,
):
    media_path = (
        "/mnt/HDDs/Movies/Movies E-I/"
        "Heat (1995)/Heat (1995).mkv"
    )

    registry = tmp_path / "cartridges.json"
    registry.write_text(
        '{"schema_version": 999}',
        encoding="utf-8",
    )

    provider = CachedCargoProvider(
        Resolver(payload(media_path)),
        cache_seconds=0,
        cartridge_registry_path=registry,
    )

    result = provider.snapshot()
    loadmaster = result["loadmaster"]

    assert loadmaster["state"] == "INVALID"
    assert "schema" in loadmaster["invalid_reason"]
