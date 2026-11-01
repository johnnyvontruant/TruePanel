"""Correlate recent Cargo Bay items with validated backup evidence."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _timestamp(value: Any) -> float | None:
    text = str(value or "").strip()

    if not text:
        return None

    try:
        parsed = datetime.fromisoformat(
            text.replace("Z", "+00:00")
        )
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)

    return parsed.timestamp()


def _canonical(path: Any) -> str | None:
    text = str(path or "").strip()

    if not text.startswith("/"):
        return None

    return str(Path(text))


def correlate_backup_manifest(
    *,
    cargo_items: list[dict[str, Any]],
    manifest: dict[str, Any] | None,
    tracking: bool,
    invalid_reason: str | None = None,
) -> dict[str, Any]:
    """Return deterministic backup state for recent cargo."""

    if not tracking:
        return {
            "tracking": False,
            "state": "NOT_TRACKED",
            "verified": 0,
            "awaiting": len(cargo_items),
            "stale": 0,
            "mismatch": 0,
            "invalid": 0,
            "total": len(cargo_items),
            "manifest_created_at": None,
            "source": None,
            "items": [],
        }

    if manifest is None:
        return {
            "tracking": True,
            "state": "INVALID",
            "verified": 0,
            "awaiting": len(cargo_items),
            "stale": 0,
            "mismatch": 0,
            "invalid": len(cargo_items),
            "total": len(cargo_items),
            "manifest_created_at": None,
            "source": None,
            "invalid_reason": (
                invalid_reason
                or "Cargo backup manifest unavailable"
            ),
            "items": [
                {
                    "current_path": item.get("current_path"),
                    "title": item.get("title"),
                    "state": "INVALID",
                }
                for item in cargo_items
            ],
        }

    evidence_by_path = {}

    for evidence in manifest.get("items", []):
        if not isinstance(evidence, dict):
            continue

        path = _canonical(evidence.get("path"))

        if path:
            evidence_by_path[path] = evidence

    results = []

    verified = 0
    awaiting = 0
    stale = 0
    mismatch = 0

    for item in cargo_items:
        current_path = _canonical(
            item.get("current_path")
        )
        title = item.get("title")
        size = item.get("size_bytes")
        imported_at = item.get("imported_at")

        state = "AWAITING"
        evidence = (
            evidence_by_path.get(current_path)
            if current_path
            else None
        )

        if evidence is None:
            awaiting += 1
        else:
            evidence_size = evidence.get("size_bytes")

            if (
                size is not None
                and evidence_size != size
            ):
                state = "MISMATCH"
                mismatch += 1
            else:
                backed_up_at = _timestamp(
                    evidence.get("backed_up_at")
                )

                if (
                    backed_up_at is None
                    or imported_at is None
                    or backed_up_at < float(imported_at)
                ):
                    state = "STALE"
                    stale += 1
                else:
                    state = "VERIFIED"
                    verified += 1

        result = {
            "title": title,
            "current_path": current_path,
            "size_bytes": size,
            "imported_at": imported_at,
            "state": state,
        }

        if evidence is not None:
            result["backed_up_at"] = evidence.get(
                "backed_up_at"
            )

            if evidence.get("sha256"):
                result["sha256"] = evidence["sha256"]

        results.append(result)

    if mismatch or stale:
        overall = "REVIEW"
    elif verified == len(cargo_items) and cargo_items:
        overall = "VERIFIED"
    elif cargo_items:
        overall = "AWAITING"
    else:
        overall = "CLEAR"

    return {
        "tracking": True,
        "state": overall,
        "verified": verified,
        "awaiting": awaiting,
        "stale": stale,
        "mismatch": mismatch,
        "invalid": 0,
        "total": len(cargo_items),
        "manifest_created_at": manifest.get("created_at"),
        "source": manifest.get("source"),
        "items": results,
    }
