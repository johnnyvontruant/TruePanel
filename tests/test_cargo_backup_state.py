from truepanel.cargo.backup_state import (
    correlate_backup_manifest,
)


def cargo(
    *,
    title="Example",
    path="/mnt/HDDs/Movies/Example.mkv",
    size=100,
    imported_at=1000.0,
):
    return {
        "title": title,
        "current_path": path,
        "size_bytes": size,
        "imported_at": imported_at,
    }


def manifest(
    *,
    path="/mnt/HDDs/Movies/Example.mkv",
    size=100,
    backed_up_at="1970-01-01T00:20:00Z",
):
    return {
        "schema_version": 1,
        "kind": "truepanel.cargo_backup_manifest",
        "created_at": "1970-01-01T00:21:00Z",
        "source": "test-backup",
        "items": [
            {
                "path": path,
                "size_bytes": size,
                "backed_up_at": backed_up_at,
            }
        ],
    }


def test_not_tracked_is_explicit():
    result = correlate_backup_manifest(
        cargo_items=[cargo()],
        manifest=None,
        tracking=False,
    )

    assert result["state"] == "NOT_TRACKED"
    assert result["tracking"] is False
    assert result["verified"] == 0
    assert result["awaiting"] == 1


def test_invalid_manifest_is_fail_closed():
    result = correlate_backup_manifest(
        cargo_items=[cargo()],
        manifest=None,
        tracking=True,
        invalid_reason="broken manifest",
    )

    assert result["state"] == "INVALID"
    assert result["tracking"] is True
    assert result["invalid"] == 1
    assert result["items"][0]["state"] == "INVALID"


def test_matching_current_path_and_size_is_verified():
    result = correlate_backup_manifest(
        cargo_items=[cargo()],
        manifest=manifest(),
        tracking=True,
    )

    assert result["state"] == "VERIFIED"
    assert result["verified"] == 1
    assert result["items"][0]["state"] == "VERIFIED"


def test_missing_evidence_is_awaiting():
    result = correlate_backup_manifest(
        cargo_items=[
            cargo(
                path="/mnt/HDDs/Movies/Missing.mkv"
            )
        ],
        manifest=manifest(),
        tracking=True,
    )

    assert result["state"] == "AWAITING"
    assert result["awaiting"] == 1
    assert result["items"][0]["state"] == "AWAITING"


def test_same_path_wrong_size_is_mismatch():
    result = correlate_backup_manifest(
        cargo_items=[cargo(size=101)],
        manifest=manifest(size=100),
        tracking=True,
    )

    assert result["state"] == "REVIEW"
    assert result["mismatch"] == 1
    assert result["items"][0]["state"] == "MISMATCH"


def test_old_backup_evidence_is_stale():
    result = correlate_backup_manifest(
        cargo_items=[
            cargo(imported_at=2000.0)
        ],
        manifest=manifest(
            backed_up_at="1970-01-01T00:20:00Z"
        ),
        tracking=True,
    )

    assert result["state"] == "REVIEW"
    assert result["stale"] == 1
    assert result["items"][0]["state"] == "STALE"


def test_current_path_wins_after_media_move():
    result = correlate_backup_manifest(
        cargo_items=[
            cargo(
                path=(
                    "/mnt/HDDs/Movies/Movies J-S/"
                    "One Night Only (2026)/"
                    "One Night Only (2026).mkv"
                )
            )
        ],
        manifest=manifest(
            path=(
                "/mnt/HDDs/Movies/Movies J-S/"
                "One Night Only (2026)/"
                "One Night Only (2026).mkv"
            )
        ),
        tracking=True,
    )

    assert result["items"][0]["state"] == "VERIFIED"


def test_optional_digest_is_preserved_without_live_hashing():
    evidence = manifest()
    evidence["items"][0]["sha256"] = "a" * 64

    result = correlate_backup_manifest(
        cargo_items=[cargo()],
        manifest=evidence,
        tracking=True,
    )

    assert (
        result["items"][0]["sha256"]
        == "a" * 64
    )


def test_empty_tracked_manifest_is_clear():
    evidence = manifest()
    evidence["items"] = []

    result = correlate_backup_manifest(
        cargo_items=[],
        manifest=evidence,
        tracking=True,
    )

    assert result["state"] == "CLEAR"
    assert result["total"] == 0
