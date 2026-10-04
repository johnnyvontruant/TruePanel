import json
from datetime import UTC, datetime

import pytest

from truepanel.cargo.receipt_sources import (
    LoadmasterReceiptSourceError,
    sdr_rescue_receipt_cargo_items,
)
from truepanel.cargo.cartridges import load_cartridge_registry


def _registry(tmp_path, media_root):
    path = tmp_path / "cartridges.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "truepanel.loadmaster_cartridge_registry",
                "cartridges": [
                    {
                        "id": "movies-num-d",
                        "label": "Movies #-D",
                        "uuid": "TEST-NUM-D",
                        "role": "movies",
                        "source_prefix": str(media_root),
                        "usb_relative_path": "Movies 1-D",
                        "allow_ingest": True,
                        "allow_backup": True,
                        "delete_policy": "never",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return load_cartridge_registry(path)


def _receipt(
    receipts,
    current,
    *,
    generated_at="2026-10-03T20:14:05.695916-07:00",
    result="PASS_REPLACED_AND_RADARR_VERIFIED",
    dynamic_range="SDR",
):
    path = receipts / "678-test.json"
    path.write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "engine": "sdr-rescue-apply-one",
                "movie_id": 678,
                "title": "Collateral",
                "year": 2004,
                "result": result,
                "final": {
                    "dynamic_range": dynamic_range,
                    "resolution": 2160,
                },
                "new_sdr_file": str(current),
            }
        ),
        encoding="utf-8",
    )
    return path


def test_receipt_source_translates_verified_sdr(tmp_path):
    media_root = tmp_path / "Movies 1-D"
    current = media_root / "Collateral (2004)" / "Collateral (2004).mkv"
    current.parent.mkdir(parents=True)
    current.write_bytes(b"x" * 128)

    receipts = tmp_path / "receipts"
    receipts.mkdir()
    _receipt(receipts, current)

    rows, report = sdr_rescue_receipt_cargo_items(
        receipts,
        cartridges=_registry(tmp_path, media_root),
    )

    assert report == {
        "files_scanned": 1,
        "items": 1,
    }
    assert len(rows) == 1
    row = rows[0]
    assert row["title"] == "Collateral"
    assert row["source"] == "sdr-rescue"
    assert row["current_path"] == str(current)
    assert row["size_bytes"] == 128
    assert row["imported_at"] == pytest.approx(
        datetime(
            2026,
            10,
            4,
            3,
            14,
            5,
            695916,
            tzinfo=UTC,
        ).timestamp()
    )


def test_receipt_source_rejects_non_sdr_final(tmp_path):
    media_root = tmp_path / "Movies 1-D"
    current = media_root / "Collateral (2004)" / "Collateral (2004).mkv"
    current.parent.mkdir(parents=True)
    current.write_bytes(b"x")

    receipts = tmp_path / "receipts"
    receipts.mkdir()
    _receipt(
        receipts,
        current,
        dynamic_range="HDR_DV",
    )

    with pytest.raises(
        LoadmasterReceiptSourceError,
        match="final probe is not SDR",
    ):
        sdr_rescue_receipt_cargo_items(
            receipts,
            cartridges=_registry(tmp_path, media_root),
        )


def test_receipt_source_rejects_unmapped_file(tmp_path):
    media_root = tmp_path / "Movies 1-D"
    media_root.mkdir()
    current = tmp_path / "Elsewhere" / "Collateral.mkv"
    current.parent.mkdir()
    current.write_bytes(b"x")

    receipts = tmp_path / "receipts"
    receipts.mkdir()
    _receipt(receipts, current)

    with pytest.raises(
        LoadmasterReceiptSourceError,
        match="no cartridge mapping",
    ):
        sdr_rescue_receipt_cargo_items(
            receipts,
            cartridges=_registry(tmp_path, media_root),
        )


def test_receipt_source_keeps_latest_receipt_per_path(tmp_path):
    media_root = tmp_path / "Movies 1-D"
    current = media_root / "Collateral (2004)" / "Collateral (2004).mkv"
    current.parent.mkdir(parents=True)
    current.write_bytes(b"x")

    receipts = tmp_path / "receipts"
    receipts.mkdir()

    first = _receipt(
        receipts,
        current,
        generated_at="2026-10-04T03:00:00+00:00",
    )
    first.rename(receipts / "678-first.json")

    _receipt(
        receipts,
        current,
        generated_at="2026-10-04T04:00:00+00:00",
    )

    rows, report = sdr_rescue_receipt_cargo_items(
        receipts,
        cartridges=_registry(tmp_path, media_root),
    )

    assert report["files_scanned"] == 2
    assert report["items"] == 1
    assert rows[0]["imported_at"] == datetime(
        2026,
        10,
        4,
        4,
        0,
        tzinfo=UTC,
    ).timestamp()
