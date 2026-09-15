"""Mission Control composition boundary for Project WINGMAN."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import WingmanMode
from .runtime_advisory import WingmanRuntimeAdvisory
from .sources import build_status_sources, load_manual_sources

BRIEF_QUESTION = "Give me the 30-second state of the system."


class WingmanBriefService:
    """Compose one fixed, advisory-only Mission Control brief."""

    def __init__(
        self,
        advisory: WingmanRuntimeAdvisory,
        *,
        docs_root: Path,
    ) -> None:
        self.advisory = advisory
        self.docs_root = Path(docs_root)

    def brief(
        self,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate a grounded brief from the public Mission Control snapshot."""

        status_sources = build_status_sources(snapshot)
        manual_sources = load_manual_sources(self.docs_root)
        sources = (*status_sources, *manual_sources)

        result, lifecycle = self.advisory.advise(
            mode=WingmanMode.BRIEF,
            question=BRIEF_QUESTION,
            sources=sources,
        )

        payload = result.as_dict()
        payload["advisory_only"] = True
        payload["lifecycle"] = {
            "runtime_started": lifecycle.runtime_started,
            "model_invoked": lifecycle.model_invoked,
            "runtime_reaped": lifecycle.runtime_reaped,
        }

        return payload


__all__ = [
    "BRIEF_QUESTION",
    "WingmanBriefService",
]
