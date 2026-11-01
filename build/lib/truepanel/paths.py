"""
Shared TruePanel installation path resolution.

Lifecycle commands must not assume a specific TrueNAS pool,
dataset name, or host-specific deployment layout.
"""

from __future__ import annotations

import os
from pathlib import Path

TRUEPANEL_ROOT_ENV = "TRUEPANEL_ROOT"


def source_root() -> Path:
    """
    Return the root containing the TruePanel Python package.
    """

    return Path(__file__).resolve().parents[1]


def installation_root(
    root: str | Path | None = None,
) -> Path:
    """
    Resolve the TruePanel installation root.

    Resolution order:

    1. Explicit caller-provided root.
    2. TRUEPANEL_ROOT environment variable.
    3. The tree containing the running TruePanel package.

    No storage pool or dataset name is assumed.
    """

    if root is not None:
        return Path(root).expanduser().resolve()

    environment_root = os.environ.get(
        TRUEPANEL_ROOT_ENV
    )

    if environment_root:
        return (
            Path(environment_root)
            .expanduser()
            .resolve()
        )

    return source_root()
