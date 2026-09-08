import json

import pytest

from truepanel.cargo.backup_manifest import (
    CARGO_BACKUP_MANIFEST_KIND,
    validate_backup_manifest,
)


def manifest():
    return {
        "schema_version": 1,
        "kind": CARGO_BACKUP_MANIFEST_KIND,
        "created_at": "2026-09-08T19:30:00Z",
        "source": "battlestation-backup",
        "items": [
            {
                "path": (
                    "/mnt/HDDs/Movies/"
                    "Example/Example.mkv"
                ),
                "size_bytes": 123456,
                "backed_up_at": (
                    "2026-09-08T19:25:00Z"
                ),
            }
        ],
    }


def write_manifest(tmp_path, payload):
    path = (
        tmp_path
        / "cargo-backup-manifest.json"
    )
    path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    return path


def test_valid_manifest_round_trip(tmp_path):
    path = write_manifest(
        tmp_path,
        manifest(),
    )

    payload = validate_backup_manifest(
        path
    )

    assert payload["schema_version"] == 1
    assert (
        payload["kind"]
        == CARGO_BACKUP_MANIFEST_KIND
    )
    assert len(payload["items"]) == 1
    assert (
        payload["items"][0]["size_bytes"]
        == 123456
    )


def test_missing_manifest_is_rejected(
    tmp_path,
):
    with pytest.raises(
        ValueError,
        match="missing Cargo backup manifest",
    ):
        validate_backup_manifest(
            tmp_path / "missing.json"
        )


def test_invalid_json_is_rejected(
    tmp_path,
):
    path = (
        tmp_path
        / "cargo-backup-manifest.json"
    )
    path.write_text(
        "{not-json",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="invalid Cargo backup manifest",
    ):
        validate_backup_manifest(path)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "schema_version",
            2,
            "unsupported Cargo backup manifest schema",
        ),
        (
            "kind",
            "something.else",
            "Cargo backup manifest kind is invalid",
        ),
        (
            "created_at",
            "",
            "Cargo backup manifest created_at is invalid",
        ),
        (
            "source",
            "",
            "Cargo backup manifest source is invalid",
        ),
        (
            "items",
            {},
            "Cargo backup manifest items must be a list",
        ),
    ],
)
def test_invalid_top_level_contract(
    tmp_path,
    field,
    value,
    message,
):
    payload = manifest()
    payload[field] = value

    path = write_manifest(
        tmp_path,
        payload,
    )

    with pytest.raises(
        ValueError,
        match=message,
    ):
        validate_backup_manifest(path)


def test_relative_item_path_is_rejected(
    tmp_path,
):
    payload = manifest()
    payload["items"][0]["path"] = (
        "Movies/Example.mkv"
    )

    path = write_manifest(
        tmp_path,
        payload,
    )

    with pytest.raises(
        ValueError,
        match="path is invalid",
    ):
        validate_backup_manifest(path)


def test_negative_size_is_rejected(
    tmp_path,
):
    payload = manifest()
    payload["items"][0]["size_bytes"] = -1

    path = write_manifest(
        tmp_path,
        payload,
    )

    with pytest.raises(
        ValueError,
        match="size_bytes is invalid",
    ):
        validate_backup_manifest(path)


def test_optional_sha256_is_normalized(
    tmp_path,
):
    payload = manifest()
    payload["items"][0]["sha256"] = "A" * 64

    path = write_manifest(
        tmp_path,
        payload,
    )

    result = validate_backup_manifest(
        path
    )

    assert (
        result["items"][0]["sha256"]
        == "a" * 64
    )


def test_invalid_sha256_is_rejected(
    tmp_path,
):
    payload = manifest()
    payload["items"][0]["sha256"] = "nope"

    path = write_manifest(
        tmp_path,
        payload,
    )

    with pytest.raises(
        ValueError,
        match="sha256 is invalid",
    ):
        validate_backup_manifest(path)
