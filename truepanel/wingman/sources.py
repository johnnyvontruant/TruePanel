"""Bounded source assembly for Project WINGMAN."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .contracts import GroundingSource

MAX_SOURCE_CHARS = 6000
STATUS_SECTIONS = (
    "system",
    "preflight",
    "operator_guidance",
    "reliability",
    "storage",
    "fans",
    "network",
    "cargo",
    "sentinel",
    "lifeline",
)
MANUAL_FILES = (
    "MISSION_CONTROL.md",
    "HARDWARE.md",
    "CARGO_BAY.md",
    "AEGIS_AIRWORTHINESS.md",
    "UPGRADING.md",
    "INSTALLATION.md",
    "CLI.md",
)
_HEADING_RE = re.compile(r"^(#{2,4})\s+(.+?)\s*$", re.MULTILINE)
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _bounded(value: str) -> str:
    value = value.strip()
    if len(value) <= MAX_SOURCE_CHARS:
        return value
    return value[: MAX_SOURCE_CHARS - 20].rstrip() + "\n[content bounded]"


def build_status_sources(payload: dict[str, Any]) -> tuple[GroundingSource, ...]:
    """Convert public Mission Control status sections into bounded sources.

    Callers must pass the same privacy-safe snapshot exposed to Mission Control,
    not raw collectors or credential-bearing provider objects. Unknown sections
    are ignored rather than forwarded to the model. Non-JSON section values are
    skipped rather than stringified into model-visible text.
    """

    sources: list[GroundingSource] = []
    for section in STATUS_SECTIONS:
        if section not in payload:
            continue
        try:
            content = json.dumps(
                payload[section],
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError):
            continue
        sources.append(
            GroundingSource(
                source_id=f"status:{section}",
                kind="mission_control_status",
                title=f"Mission Control {section.replace('_', ' ').title()}",
                content=_bounded(content),
            )
        )
    return tuple(sources)


def _slug(value: str) -> str:
    return _SLUG_RE.sub("-", value.lower()).strip("-") or "section"


def _manual_chunks(path: Path) -> tuple[GroundingSource, ...]:
    text = path.read_text(encoding="utf-8")
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return (
            GroundingSource(
                source_id=f"manual:{path.name}:document",
                kind="manual",
                title=path.stem.replace("_", " ").title(),
                content=_bounded(text),
            ),
        )

    chunks: list[GroundingSource] = []
    intro = text[: matches[0].start()].strip()
    if intro:
        chunks.append(
            GroundingSource(
                source_id=f"manual:{path.name}:intro",
                kind="manual",
                title=f"{path.stem.replace('_', ' ').title()} Introduction",
                content=_bounded(intro),
            )
        )
    seen: dict[str, int] = {}
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        heading = match.group(2).strip()
        slug = _slug(heading)
        seen[slug] = seen.get(slug, 0) + 1
        suffix = f"-{seen[slug]}" if seen[slug] > 1 else ""
        chunks.append(
            GroundingSource(
                source_id=f"manual:{path.name}:{slug}{suffix}",
                kind="manual",
                title=f"{path.stem.replace('_', ' ').title()} · {heading}",
                content=_bounded(text[start:end]),
            )
        )
    return tuple(chunks)


def load_manual_sources(docs_root: Path) -> tuple[GroundingSource, ...]:
    """Load only the maintained WINGMAN manual allowlist from ``docs_root``."""

    sources: list[GroundingSource] = []
    resolved_root = docs_root.resolve()
    for name in MANUAL_FILES:
        path = (resolved_root / name).resolve()
        if path.parent != resolved_root or not path.is_file():
            continue
        sources.extend(_manual_chunks(path))
    return tuple(sources)


__all__ = [
    "MANUAL_FILES",
    "MAX_SOURCE_CHARS",
    "STATUS_SECTIONS",
    "build_status_sources",
    "load_manual_sources",
]
