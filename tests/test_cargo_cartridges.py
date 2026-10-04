import json

import pytest

from truepanel.cargo.cartridges import (
    LOADMASTER_REGISTRY_KIND,
    assign_cartridge,
    disabled_loadmaster_summary,
    load_cartridge_registry,
    summarize_cartridge_cargo,
)


def write_registry(tmp_path, cartridges):
    path = tmp_path / "cartridges.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": LOADMASTER_REGISTRY_KIND,
                "cartridges": cartridges,
            }
        ),
        encoding="utf-8",
    )
    return path


def movie_cartridge(
    cartridge_id="movies-e-i",
    label="Movies E-I",
    uuid="E-I",
):
    return {
        "id": cartridge_id,
        "label": label,
        "uuid": uuid,
        "role": "movies",
        "source_prefix": (
            "/mnt/HDDs/Movies/Movies E-I"
        ),
        "usb_relative_path": "Movies E-I",
        "allow_ingest": True,
        "allow_backup": True,
        "delete_policy": "never",
    }


def test_load_registry_and_assign_longest_prefix(
    tmp_path,
):
    broad = movie_cartridge(
        "movies-all",
        "Movies",
        "ALL",
    )
    broad["source_prefix"] = (
        "/mnt/HDDs/Movies"
    )
    broad["usb_relative_path"] = "Movies"

    specific = movie_cartridge()

    cartridges = load_cartridge_registry(
        write_registry(
            tmp_path,
            [broad, specific],
        )
    )

    result = assign_cartridge(
        (
            "/mnt/HDDs/Movies/Movies E-I/"
            "Heat (1995)/Heat (1995).mkv"
        ),
        cartridges,
    )

    assert result is not None
    assert (
        result.cartridge_id
        == "movies-e-i"
    )


def test_registry_rejects_duplicate_uuid(
    tmp_path,
):
    first = movie_cartridge()
    second = movie_cartridge(
        "movies-j-s",
        "Movies J-S",
        "e-i",
    )
    second["source_prefix"] = (
        "/mnt/HDDs/Movies/Movies J-S"
    )
    second["usb_relative_path"] = (
        "Movies J-S"
    )

    with pytest.raises(
        ValueError,
        match="duplicate.*uuid",
    ):
        load_cartridge_registry(
            write_registry(
                tmp_path,
                [first, second],
            )
        )


def test_registry_rejects_delete_policy_other_than_never(
    tmp_path,
):
    item = movie_cartridge()
    item["delete_policy"] = "mirror"

    with pytest.raises(
        ValueError,
        match="delete_policy",
    ):
        load_cartridge_registry(
            write_registry(
                tmp_path,
                [item],
            )
        )


def test_registry_rejects_absolute_usb_relative_path(
    tmp_path,
):
    item = movie_cartridge()
    item["usb_relative_path"] = (
        "/Movies E-I"
    )

    with pytest.raises(
        ValueError,
        match="must be relative",
    ):
        load_cartridge_registry(
            write_registry(
                tmp_path,
                [item],
            )
        )


def test_summarize_groups_pending_by_cartridge(
    tmp_path,
):
    cartridges = load_cartridge_registry(
        write_registry(
            tmp_path,
            [movie_cartridge()],
        )
    )

    path = (
        "/mnt/HDDs/Movies/Movies E-I/"
        "Heat (1995)/Heat (1995).mkv"
    )

    result = summarize_cartridge_cargo(
        cargo_items=[
            {
                "title": "Heat",
                "detail": "Heat (1995)",
                "source": "radarr",
                "current_path": path,
                "size_bytes": 123,
            }
        ],
        backup={
            "items": [
                {
                    "current_path": path,
                    "state": "AWAITING",
                }
            ]
        },
        cartridges=cartridges,
    )

    assert result["state"] == "AWAITING"
    assert result["pending_items"] == 1
    assert result["pending_bytes"] == 123
    assert (
        result["next_cartridge"]["label"]
        == "Movies E-I"
    )
    assert (
        result["cartridges"][0][
            "pending_items"
        ]
        == 1
    )


def test_verified_item_is_not_pending(
    tmp_path,
):
    cartridges = load_cartridge_registry(
        write_registry(
            tmp_path,
            [movie_cartridge()],
        )
    )

    path = (
        "/mnt/HDDs/Movies/Movies E-I/"
        "Test/Test.mkv"
    )

    result = summarize_cartridge_cargo(
        cargo_items=[
            {
                "title": "Test",
                "current_path": path,
                "size_bytes": 50,
            }
        ],
        backup={
            "items": [
                {
                    "current_path": path,
                    "state": "VERIFIED",
                }
            ]
        },
        cartridges=cartridges,
    )

    assert result["state"] == "CLEAR"
    assert result["pending_items"] == 0
    assert (
        result["cartridges"][0][
            "verified_items"
        ]
        == 1
    )


def test_unmapped_item_forces_review(
    tmp_path,
):
    cartridges = load_cartridge_registry(
        write_registry(
            tmp_path,
            [movie_cartridge()],
        )
    )

    result = summarize_cartridge_cargo(
        cargo_items=[
            {
                "title": "Outside",
                "current_path": (
                    "/mnt/HDDs/Movies/"
                    "Movies T-Z/Test.mkv"
                ),
                "size_bytes": 10,
            }
        ],
        backup={"items": []},
        cartridges=cartridges,
    )

    assert result["state"] == "REVIEW"
    assert result["unmapped_items"] == 1
    assert (
        result["unmapped"][0]["reason"]
        == "NO_CARTRIDGE"
    )


def test_mismatch_is_pending_and_review(
    tmp_path,
):
    cartridges = load_cartridge_registry(
        write_registry(
            tmp_path,
            [movie_cartridge()],
        )
    )

    path = (
        "/mnt/HDDs/Movies/Movies E-I/"
        "Test/Test.mkv"
    )

    result = summarize_cartridge_cargo(
        cargo_items=[
            {
                "title": "Test",
                "current_path": path,
                "size_bytes": 10,
            }
        ],
        backup={
            "items": [
                {
                    "current_path": path,
                    "state": "MISMATCH",
                }
            ]
        },
        cartridges=cartridges,
    )

    assert result["state"] == "REVIEW"
    assert result["pending_items"] == 1
    assert result["review_items"] == 1


def test_disabled_summary_is_explicit():
    result = disabled_loadmaster_summary()

    assert result["enabled"] is False
    assert result["state"] == "DISABLED"
    assert result["read_only"] is True
