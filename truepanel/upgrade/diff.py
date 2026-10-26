"""What promoting a tree would change in the deployment, compared by content.

Runs the promotion's own rsync in dry-run mode with checksums (``-n -c``), so
the listing is exactly what ``--promote`` would add, change and delete,
ignoring timestamps that differ only because the tree was freshly checked out.
The build stamp is left out: staging always writes a fresh one, and a source
checkout never has one.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from truepanel.build import BUILD_FILE

from .checks import command_detail, run_command

DIFF_TIMEOUT_SECONDS = 600.0
SHOWN_PER_KIND = 60


@dataclass
class ContentChanges:
    added: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.added) + len(self.changed) + len(self.deleted)


def diff_command(source: Path, deploy_root: Path) -> list[str]:
    from .promotion import PROMOTION_DEPLOY_EXCLUDES, PROMOTION_EXCLUDES

    return [
        "rsync",
        "-n",
        "-a",
        "-c",
        "--delete",
        "--itemize-changes",
        *(
            f"--exclude={item}"
            for item in (*PROMOTION_EXCLUDES, *PROMOTION_DEPLOY_EXCLUDES, BUILD_FILE)
        ),
        f"{source}/",
        f"{deploy_root}/",
    ]


def parse_itemized(output: str) -> ContentChanges:
    changes = ContentChanges()
    for line in output.splitlines():
        if line.startswith("*deleting "):
            path = line[len("*deleting ") :].strip()
            if path and not path.endswith("/"):
                changes.deleted.append(path)
        elif line.startswith(">f") and " " in line:
            flags, _, path = line.partition(" ")
            (changes.added if "+++++++" in flags else changes.changed).append(
                path.strip()
            )
    return changes


def content_changes(
    source: Path,
    deploy_root: Path,
    *,
    runner: Callable[..., Any] = run_command,
) -> tuple[ContentChanges | None, str]:
    """Return (changes, "") or (None, why it could not be computed)."""

    try:
        response = runner(
            diff_command(source, deploy_root), timeout=DIFF_TIMEOUT_SECONDS
        )
    except Exception as error:  # noqa: BLE001 - a diff must never block an upgrade
        return None, str(error)
    if response.returncode != 0:
        return None, command_detail(response)
    return parse_itemized(response.stdout), ""


def print_changes(changes: ContentChanges | None, error: str = "") -> None:
    print("\nChanges on promotion (compared by content):")
    if changes is None:
        print(f"  could not be listed: {error}")
        return
    print(
        f"  {len(changes.changed)} changed, {len(changes.added)} added, "
        f"{len(changes.deleted)} deleted"
    )
    for label, paths in (
        ("changed", changes.changed),
        ("added", changes.added),
        ("deleted", changes.deleted),
    ):
        for path in paths[:SHOWN_PER_KIND]:
            print(f"  {label:<8} {path}")
        if len(paths) > SHOWN_PER_KIND:
            print(f"  {label:<8} … and {len(paths) - SHOWN_PER_KIND} more")


__all__ = [
    "ContentChanges",
    "content_changes",
    "diff_command",
    "parse_itemized",
    "print_changes",
]
