import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from truepanel.cargo.backup_manifest import (
    validate_backup_manifest,
)
from truepanel.cargo.backup_producer import (
    BackupMapping,
    BackupProducerError,
    build_backup_manifest,
    map_backup_path,
    run,
    write_manifest_atomic,
)

NOW = datetime(
    2026,
    9,
    8,
    20,
    30,
    tzinfo=UTC,
)


def cargo_payload(
    source: Path,
    size: int,
):
    return {
        "schema_version": 1,
        "cargo_bay": {
            "groups": {
                "tv": [
                    {
                        "title": "Example",
                        "current_path": str(
                            source
                        ),
                        "size_bytes": size,
                        "imported_at": 1000.0,
                        "exists": True,
                    }
                ],
                "movies": [],
            }
        },
    }


def mapping(
    source_root: Path,
    backup_root: Path,
):
    return BackupMapping(
        source_prefix=source_root,
        backup_prefix=backup_root,
    )


def test_map_backup_path_preserves_relative_path(
    tmp_path,
):
    source_root = Path(
        "/mnt/HDDs/Shows"
    )
    backup_root = (
        tmp_path / "Shows"
    )

    result = map_backup_path(
        source_root
        / "TV N-Z"
        / "Vigil"
        / "3x04.mkv",
        [
            mapping(
                source_root,
                backup_root,
            )
        ],
    )

    assert result == (
        backup_root
        / "TV N-Z"
        / "Vigil"
        / "3x04.mkv"
    )


def test_longest_mapping_wins(
    tmp_path,
):
    result = map_backup_path(
        Path(
            "/mnt/HDDs/Shows/A/file.mkv"
        ),
        [
            mapping(
                Path("/mnt/HDDs"),
                tmp_path / "all",
            ),
            mapping(
                Path("/mnt/HDDs/Shows"),
                tmp_path / "shows",
            ),
        ],
    )

    assert result == (
        tmp_path
        / "shows"
        / "A"
        / "file.mkv"
    )


def test_unmapped_path_returns_none(
    tmp_path,
):
    result = map_backup_path(
        Path("/different/file.mkv"),
        [
            mapping(
                Path("/mnt/HDDs"),
                tmp_path / "backup",
            )
        ],
    )

    assert result is None


def test_verified_backup_emits_evidence(
    tmp_path,
):
    source_root = Path(
        "/mnt/HDDs/Shows"
    )

    source = (
        source_root
        / "TV N-Z"
        / "Vigil"
        / "3x04.mkv"
    )

    backup_root = (
        tmp_path / "Shows"
    )

    backup = (
        backup_root
        / "TV N-Z"
        / "Vigil"
        / "3x04.mkv"
    )

    backup.parent.mkdir(
        parents=True
    )
    backup.write_bytes(
        b"x" * 100
    )

    manifest, report = (
        build_backup_manifest(
            cargo_payload=cargo_payload(
                source,
                100,
            ),
            mappings=[
                mapping(
                    source_root,
                    backup_root,
                )
            ],
            observed_at=NOW,
        )
    )

    assert report["verified"] == 1
    assert report["mismatch"] == 0
    assert report["missing"] == 0

    assert manifest["items"] == [
        {
            "path": str(source),
            "size_bytes": 100,
            "backed_up_at": (
                "2026-09-08T20:30:00+00:00"
            ),
        }
    ]


def test_missing_backup_emits_no_evidence(
    tmp_path,
):
    source = Path(
        "/mnt/HDDs/Shows/Missing.mkv"
    )

    manifest, report = (
        build_backup_manifest(
            cargo_payload=cargo_payload(
                source,
                100,
            ),
            mappings=[
                mapping(
                    Path(
                        "/mnt/HDDs/Shows"
                    ),
                    tmp_path / "Shows",
                )
            ],
            observed_at=NOW,
        )
    )

    assert manifest["items"] == []
    assert report["missing"] == 1


def test_size_mismatch_emits_observed_size(
    tmp_path,
):
    source = Path(
        "/mnt/HDDs/Shows/Test.mkv"
    )

    backup_root = (
        tmp_path / "Shows"
    )
    backup_root.mkdir()

    backup = (
        backup_root
        / "Test.mkv"
    )

    backup.write_bytes(
        b"x" * 99
    )

    manifest, report = (
        build_backup_manifest(
            cargo_payload=cargo_payload(
                source,
                100,
            ),
            mappings=[
                mapping(
                    Path(
                        "/mnt/HDDs/Shows"
                    ),
                    backup_root,
                )
            ],
            observed_at=NOW,
        )
    )

    assert report["mismatch"] == 1
    assert (
        manifest["items"][0][
            "size_bytes"
        ]
        == 99
    )


def test_unmapped_is_reported_but_not_claimed(
    tmp_path,
):
    source = Path(
        "/mnt/HDDs/Movies/Test.mkv"
    )

    manifest, report = (
        build_backup_manifest(
            cargo_payload=cargo_payload(
                source,
                100,
            ),
            mappings=[
                mapping(
                    Path(
                        "/mnt/HDDs/Shows"
                    ),
                    tmp_path / "Shows",
                )
            ],
            observed_at=NOW,
        )
    )

    assert report["unmapped"] == 1
    assert manifest["items"] == []


def test_symlink_backup_is_rejected(
    tmp_path,
):
    source = Path(
        "/mnt/HDDs/Shows/Test.mkv"
    )

    backup_root = (
        tmp_path / "Shows"
    )
    backup_root.mkdir()

    target = (
        tmp_path / "target.mkv"
    )
    target.write_bytes(
        b"x" * 100
    )

    (
        backup_root
        / "Test.mkv"
    ).symlink_to(
        target
    )

    with pytest.raises(
        BackupProducerError,
        match="symlink",
    ):
        build_backup_manifest(
            cargo_payload=cargo_payload(
                source,
                100,
            ),
            mappings=[
                mapping(
                    Path(
                        "/mnt/HDDs/Shows"
                    ),
                    backup_root,
                )
            ],
            observed_at=NOW,
        )


def test_directory_backup_is_rejected(
    tmp_path,
):
    source = Path(
        "/mnt/HDDs/Shows/Test.mkv"
    )

    backup_root = (
        tmp_path / "Shows"
    )
    backup_root.mkdir()

    (
        backup_root / "Test.mkv"
    ).mkdir()

    with pytest.raises(
        BackupProducerError,
        match="regular file",
    ):
        build_backup_manifest(
            cargo_payload=cargo_payload(
                source,
                100,
            ),
            mappings=[
                mapping(
                    Path(
                        "/mnt/HDDs/Shows"
                    ),
                    backup_root,
                )
            ],
            observed_at=NOW,
        )


def test_atomic_writer_creates_valid_manifest(
    tmp_path,
):
    source = Path(
        "/mnt/HDDs/Shows/Test.mkv"
    )

    backup_root = (
        tmp_path / "Shows"
    )
    backup_root.mkdir()

    (
        backup_root / "Test.mkv"
    ).write_bytes(
        b"x" * 100
    )

    manifest, _ = (
        build_backup_manifest(
            cargo_payload=cargo_payload(
                source,
                100,
            ),
            mappings=[
                mapping(
                    Path(
                        "/mnt/HDDs/Shows"
                    ),
                    backup_root,
                )
            ],
            observed_at=NOW,
        )
    )

    output = (
        tmp_path / "manifest.json"
    )

    write_manifest_atomic(
        output,
        manifest,
    )

    validated = (
        validate_backup_manifest(
            output
        )
    )

    assert len(
        validated["items"]
    ) == 1


def test_atomic_writer_replaces_previous_manifest(
    tmp_path,
):
    output = (
        tmp_path / "manifest.json"
    )

    output.write_text(
        '{"old": true}\n'
    )

    manifest = {
        "schema_version": 1,
        "kind": (
            "truepanel.cargo_backup_manifest"
        ),
        "created_at": (
            "2026-09-08T20:30:00+00:00"
        ),
        "source": "test",
        "items": [],
    }

    write_manifest_atomic(
        output,
        manifest,
    )

    assert (
        json.loads(
            output.read_text()
        )["kind"]
        == "truepanel.cargo_backup_manifest"
    )


def test_writer_rejects_relative_output():
    with pytest.raises(
        BackupProducerError,
        match="absolute",
    ):
        write_manifest_atomic(
            Path("manifest.json"),
            {},
        )


def test_cli_end_to_end(
    tmp_path,
):
    source_root = Path(
        "/mnt/HDDs/Shows"
    )
    source = (
        source_root / "Test.mkv"
    )

    backup_root = (
        tmp_path / "Shows"
    )
    backup_root.mkdir()

    (
        backup_root / "Test.mkv"
    ).write_bytes(
        b"x" * 100
    )

    cargo_json = (
        tmp_path / "cargo.json"
    )

    cargo_json.write_text(
        json.dumps(
            cargo_payload(
                source,
                100,
            )
        )
    )

    output = (
        tmp_path / "manifest.json"
    )

    report = (
        tmp_path / "report.json"
    )

    result = run(
        [
            "--cargo-json",
            str(cargo_json),
            "--map",
            (
                f"{source_root}="
                f"{backup_root}"
            ),
            "--output",
            str(output),
            "--report",
            str(report),
        ],
        clock=lambda: NOW,
    )

    assert result == 0
    assert output.exists()
    assert report.exists()

    manifest = (
        validate_backup_manifest(
            output
        )
    )

    assert len(
        manifest["items"]
    ) == 1


def test_producer_never_requires_source_file_to_exist(
    tmp_path,
):
    """
    The producer observes the independent backup only.

    It consumes source identity from Cargo Bay and does not mutate
    or open BattleStation media itself.
    """

    source = Path(
        "/mnt/HDDs/Shows/NotMountedHere.mkv"
    )

    backup_root = (
        tmp_path / "Shows"
    )
    backup_root.mkdir()

    (
        backup_root
        / "NotMountedHere.mkv"
    ).write_bytes(
        b"x" * 100
    )

    manifest, report = (
        build_backup_manifest(
            cargo_payload=cargo_payload(
                source,
                100,
            ),
            mappings=[
                mapping(
                    Path(
                        "/mnt/HDDs/Shows"
                    ),
                    backup_root,
                )
            ],
            observed_at=NOW,
        )
    )

    assert report["verified"] == 1
    assert len(
        manifest["items"]
    ) == 1
