"""Canonical, dependency-light experiment registry for Project HANGAR."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

HANGAR_STATES = ("FUTURE", "IN_PROGRESS", "COMPLETED", "FAILED")
_ID = re.compile(r"^TP-EXP-[0-9]{4}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMON = (
    "id",
    "title",
    "state",
    "hypothesis",
    "value",
    "prior_art",
    "safety_class",
    "development",
    "protocol",
    "fixtures",
    "success_criteria",
    "abort_criteria",
    "evidence",
    "outcome",
    "invalidated_assumptions",
    "reproduction",
    "revisit_conditions",
    "strongest_follow_up",
    "freshness",
)


def registry_path() -> Path:
    return Path(__file__).with_name("registry.json")


def load_registry(path: str | Path | None = None) -> dict[str, Any]:
    """Load the canonical registry from the package or an explicit path."""

    return json.loads(Path(path or registry_path()).read_text(encoding="utf-8"))


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_registry(
    registry: dict[str, Any] | None = None,
    *,
    root: str | Path | None = None,
) -> tuple[str, ...]:
    """Return deterministic CI violations for the canonical experiment memory."""

    data = registry or load_registry()
    errors: list[str] = []
    if data.get("schema_version") != 1:
        errors.append("registry: unsupported schema_version")
    if data.get("states") != list(HANGAR_STATES):
        errors.append("registry: primary states must match the HANGAR contract exactly")
    if not _text(data.get("updated_at")):
        errors.append("registry: updated_at is required")
    experiments = data.get("experiments")
    if not isinstance(experiments, list):
        return tuple(errors + ["registry: experiments must be a list"])

    ids: set[str] = set()
    repo_root = Path(root).resolve() if root else None
    for experiment in experiments:
        if not isinstance(experiment, dict):
            errors.append("registry: experiment entries must be objects")
            continue
        experiment_id = str(experiment.get("id", ""))
        prefix = experiment_id or "<missing-id>"
        if not _ID.fullmatch(experiment_id):
            errors.append(f"{prefix}: invalid stable experiment ID")
        if experiment_id in ids:
            errors.append(f"{prefix}: duplicate experiment ID")
        ids.add(experiment_id)
        for field in _COMMON:
            if field not in experiment:
                errors.append(f"{prefix}: missing {field}")

        state = experiment.get("state")
        if state not in HANGAR_STATES:
            errors.append(f"{prefix}: invalid primary state {state!r}")
        for field in ("title", "hypothesis", "value", "safety_class"):
            if not _text(experiment.get(field)):
                errors.append(f"{prefix}: {field} must be non-empty")
        for field in (
            "prior_art",
            "protocol",
            "fixtures",
            "success_criteria",
            "abort_criteria",
            "evidence",
            "invalidated_assumptions",
            "reproduction",
            "revisit_conditions",
        ):
            if not isinstance(experiment.get(field), list):
                errors.append(f"{prefix}: {field} must be a list")

        development = experiment.get("development")
        if not isinstance(development, dict):
            errors.append(f"{prefix}: development must be an object")
            development = {}
        freshness = experiment.get("freshness")
        if not isinstance(freshness, dict) or not all(
            _text(freshness.get(field)) for field in ("reviewed_at", "review_after")
        ):
            errors.append(f"{prefix}: freshness requires reviewed_at and review_after")

        outcome = experiment.get("outcome")
        if not isinstance(outcome, dict):
            errors.append(f"{prefix}: outcome must be an object")
            outcome = {}
        if state == "COMPLETED":
            if not _text(outcome.get("conclusion")):
                errors.append(f"{prefix}: completed experiment needs a conclusion")
            if not experiment.get("evidence") or not experiment.get("reproduction"):
                errors.append(f"{prefix}: completed experiment needs reproducible evidence")
        elif state == "FAILED":
            for field in ("failure_mode", "reusable_lesson"):
                if not _text(outcome.get(field)):
                    errors.append(f"{prefix}: failed experiment needs {field}")
            if not experiment.get("evidence"):
                errors.append(f"{prefix}: failed experiment needs evidence")
        elif state == "IN_PROGRESS":
            for field in ("branch", "next_test", "exit_criteria"):
                if not _text(development.get(field)):
                    errors.append(f"{prefix}: active experiment needs {field}")

        for artifact in experiment.get("evidence", []):
            if not isinstance(artifact, dict):
                errors.append(f"{prefix}: evidence entries must be objects")
                continue
            path = artifact.get("path")
            digest = artifact.get("sha256")
            if not _text(path) or not _SHA256.fullmatch(str(digest or "")):
                errors.append(f"{prefix}: evidence requires path and SHA-256")
                continue
            if repo_root is not None and artifact.get("verify_file", True):
                candidate = (repo_root / str(path)).resolve()
                if repo_root not in candidate.parents:
                    errors.append(f"{prefix}: evidence path escapes repository")
                elif not candidate.is_file():
                    errors.append(f"{prefix}: evidence file missing: {path}")
                elif hashlib.sha256(candidate.read_bytes()).hexdigest() != digest:
                    errors.append(f"{prefix}: evidence digest mismatch: {path}")
    return tuple(errors)


def status_summary(registry: dict[str, Any] | None = None) -> dict[str, int]:
    data = registry or load_registry()
    counts = Counter(item.get("state") for item in data.get("experiments", []))
    return {state: counts[state] for state in HANGAR_STATES}


def _render_state(data: dict[str, Any], state: str) -> str:
    items = [item for item in data["experiments"] if item["state"] == state]
    lines = [
        f"# HANGAR · {state.replace('_', ' ').title()}",
        "",
        "> Generated from `truepanel/hangar/registry.json`; edit the registry, not this view.",
        "",
        f"Registry version {data['registry_version']} · refreshed {data['updated_at']} · {len(items)} experiment(s)",
        "",
    ]
    if not items:
        lines.append("No experiments currently occupy this state.")
    for item in sorted(items, key=lambda value: value["id"]):
        lines.extend(
            [
                f"## {item['id']} · {item['title']}",
                "",
                item["outcome"].get("conclusion")
                or item["outcome"].get("failure_mode")
                or item["hypothesis"],
                "",
                f"- Safety: `{item['safety_class']}`",
                f"- Strongest follow-up: {item['strongest_follow_up']}",
                f"- Revisit when: {'; '.join(item['revisit_conditions']) or 'Not scheduled'}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def render_status_views(
    output: str | Path,
    registry: dict[str, Any] | None = None,
) -> dict[str, Path]:
    """Generate all four stable status views without moving source documents."""

    data = registry or load_registry()
    target = Path(output)
    target.mkdir(parents=True, exist_ok=True)
    rendered = {}
    for state in HANGAR_STATES:
        path = target / f"{state.lower()}.md"
        path.write_text(_render_state(data, state), encoding="utf-8")
        rendered[state] = path
    return rendered


__all__ = [
    "HANGAR_STATES",
    "load_registry",
    "registry_path",
    "render_status_views",
    "status_summary",
    "validate_registry",
]
