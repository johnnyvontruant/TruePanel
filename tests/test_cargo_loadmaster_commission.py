import json
from datetime import UTC, datetime

import pytest

from truepanel.cargo.commission import (
    ZERO_DELTA_CONFIRMATION,
    LoadmasterCommissionError,
    capture_zero_delta_baselines,
)
from truepanel.cargo.loadmaster import load_inventory


NOW = datetime(
    2026,
    10,
    3,
    20,
    0,
    tzinfo=UTC,
)


def write_registry(tmp_path, source):
    registry = tmp_path / "cartridges.json"
    registry.write_text(
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
                        "uuid": "PLACEHOLDER",
                        "role": "movies",
                        "source_prefix": str(source),
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
    return registry


def test_commission_requires_explicit_zero_delta_confirmation(
    tmp_path,
):
    source = tmp_path / "nas"
    source.mkdir()
    inventory = tmp_path / "inventory"
    inventory.mkdir()

    with pytest.raises(
        LoadmasterCommissionError,
        match="confirmation",
    ):
        capture_zero_delta_baselines(
            registry_path=write_registry(
                tmp_path,
                source,
            ),
            inventory_dir=inventory,
            confirmation="NO",
            captured_at=NOW,
        )


def test_commission_captures_nas_inventory(
    tmp_path,
):
    source = tmp_path / "nas"
    movie = source / "Heat (1995)"
    movie.mkdir(parents=True)
    (movie / "Heat (1995).mkv").write_bytes(
        b"movie"
    )
    (
        movie / ".media-identity.json"
    ).write_text(
        "{}",
        encoding="utf-8",
    )

    inventory = tmp_path / "inventory"
    inventory.mkdir()

    report = capture_zero_delta_baselines(
        registry_path=write_registry(
            tmp_path,
            source,
        ),
        inventory_dir=inventory,
        confirmation=ZERO_DELTA_CONFIRMATION,
        captured_at=NOW,
    )

    assert report["state"] == "BASELINE_CAPTURED"
    assert report["cartridges"][0]["files"] == 2

    loaded = load_inventory(
        inventory / "movies-e-i.json",
        cartridge_id="movies-e-i",
    )

    assert (
        "Heat (1995)/Heat (1995).mkv"
        in loaded
    )
    assert (
        "Heat (1995)/.media-identity.json"
        in loaded
    )


def test_commission_refuses_to_replace_existing_inventory(
    tmp_path,
):
    source = tmp_path / "nas"
    source.mkdir()

    inventory = tmp_path / "inventory"
    inventory.mkdir()
    (
        inventory / "movies-e-i.json"
    ).write_text(
        "{}",
        encoding="utf-8",
    )

    with pytest.raises(
        LoadmasterCommissionError,
        match="overwrite",
    ):
        capture_zero_delta_baselines(
            registry_path=write_registry(
                tmp_path,
                source,
            ),
            inventory_dir=inventory,
            confirmation=ZERO_DELTA_CONFIRMATION,
            captured_at=NOW,
        )
