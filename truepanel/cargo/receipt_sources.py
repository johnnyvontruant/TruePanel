"""Translate SDR Rescue receipts into Loadmaster cargo rows."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .cartridges import CartridgeDefinition, assign_cartridge


class LoadmasterReceiptSourceError(RuntimeError):
    """Fail-closed SDR Rescue receipt ingestion error."""


_ALLOWED_RESULTS = {
    "PASS_REPLACED_AND_RADARR_VERIFIED",
    "REPLACED_RADARR_RESCAN_PENDING",
}


def _parse_generated_at(value: Any) -> datetime:
    text = str(value or "").strip()

    if not text:
        raise LoadmasterReceiptSourceError(
            "SDR Rescue receipt generated_at is invalid"
        )

    try:
        parsed = datetime.fromisoformat(
            text.replace("Z", "+00:00")
        )
    except ValueError as error:
        raise LoadmasterReceiptSourceError(
            "SDR Rescue receipt generated_at is invalid"
        ) from error

    if parsed.tzinfo is None:
        raise LoadmasterReceiptSourceError(
            "SDR Rescue receipt generated_at must include timezone"
        )

    return parsed.astimezone(UTC)


def _load_receipt(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(
                encoding="utf-8",
            )
        )
    except (OSError, json.JSONDecodeError) as error:
        raise LoadmasterReceiptSourceError(
            f"invalid SDR Rescue receipt {path}: {error}"
        ) from error

    if not isinstance(payload, dict):
        raise LoadmasterReceiptSourceError(
            f"invalid SDR Rescue receipt {path}: expected object"
        )

    return payload


def sdr_rescue_receipt_cargo_items(
    path: Path,
    *,
    cartridges: list[CartridgeDefinition],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Return one latest cargo row per canonical SDR Rescue media path."""

    if not path.is_dir():
        raise LoadmasterReceiptSourceError(
            f"SDR Rescue receipts directory is unavailable: {path}"
        )

    files = sorted(path.glob("*.json"))
    by_path: dict[str, tuple[datetime, dict[str, Any]]] = {}

    for receipt_path in files:
        receipt = _load_receipt(
            receipt_path
        )

        if receipt.get("engine") != "sdr-rescue-apply-one":
            raise LoadmasterReceiptSourceError(
                "unexpected SDR Rescue receipt engine: "
                f"{receipt_path}"
            )

        result = str(
            receipt.get("result") or ""
        ).strip()

        if result not in _ALLOWED_RESULTS:
            raise LoadmasterReceiptSourceError(
                "unsupported SDR Rescue receipt result "
                f"{result!r}: {receipt_path}"
            )

        generated = _parse_generated_at(
            receipt.get("generated_at")
        )

        final_probe = receipt.get("final")

        if not isinstance(final_probe, dict):
            raise LoadmasterReceiptSourceError(
                f"SDR Rescue receipt final probe is invalid: {receipt_path}"
            )

        if final_probe.get("dynamic_range") != "SDR":
            raise LoadmasterReceiptSourceError(
                "SDR Rescue receipt final probe is not SDR: "
                f"{receipt_path}"
            )

        current = Path(
            str(
                receipt.get("new_sdr_file")
                or ""
            ).strip()
        )

        if not current.is_absolute():
            raise LoadmasterReceiptSourceError(
                "SDR Rescue receipt path must be absolute: "
                f"{receipt_path}"
            )

        if current.is_symlink():
            raise LoadmasterReceiptSourceError(
                "SDR Rescue canonical file may not be a symlink: "
                f"{current}"
            )

        if not current.is_file():
            raise LoadmasterReceiptSourceError(
                "SDR Rescue canonical file is unavailable: "
                f"{current}"
            )

        cartridge = assign_cartridge(
            current,
            cartridges,
        )

        if cartridge is None:
            raise LoadmasterReceiptSourceError(
                "SDR Rescue receipt has no cartridge mapping: "
                f"{current}"
            )

        movie_id = receipt.get("movie_id")
        title = receipt.get("title")

        row = {
            "title": title,
            "detail": (
                f"SDR Rescue receipt movie_id={movie_id}"
                if movie_id is not None
                else "SDR Rescue receipt"
            ),
            "source": "sdr-rescue",
            "current_path": str(current),
            "size_bytes": current.stat().st_size,
            "imported_at": generated.timestamp(),
        }

        key = str(current)
        previous = by_path.get(key)

        if previous is None or generated > previous[0]:
            by_path[key] = (
                generated,
                row,
            )

    rows = [
        value[1]
        for _, value in sorted(
            by_path.items()
        )
    ]

    return rows, {
        "files_scanned": len(files),
        "items": len(rows),
    }
