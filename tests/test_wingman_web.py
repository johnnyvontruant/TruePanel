from __future__ import annotations

from pathlib import Path

from truepanel.wingman.runtime_advisory import RuntimeAdvisoryObservation
from truepanel.wingman.service import WingmanServiceResult
from truepanel.wingman.web import BRIEF_QUESTION, WingmanBriefService


class FakeAdvisory:
    def __init__(self) -> None:
        self.calls = []

    def advise(
        self,
        *,
        mode,
        question,
        sources,
    ):
        self.calls.append(
            {
                "mode": mode,
                "question": question,
                "sources": sources,
            }
        )

        return (
            WingmanServiceResult(
                status="EXPLAINED",
                advisory={
                    "schema_version": 1,
                    "mode": "brief",
                    "status": "EXPLAINED",
                    "summary": "System healthy.",
                    "summary_source_ids": ["status:system"],
                    "observations": [],
                    "next_steps": [],
                    "uncertainty": [],
                    "control_authority": False,
                    "production_mutation": False,
                },
                source_ids=("status:system",),
                errors=(),
            ),
            RuntimeAdvisoryObservation(
                runtime_started=True,
                model_invoked=True,
                runtime_reaped=True,
            ),
        )


def test_brief_uses_fixed_question_and_allowlisted_snapshot(tmp_path: Path):
    (tmp_path / "MISSION_CONTROL.md").write_text(
        "## Overview\nMission Control operator overview.\n",
        encoding="utf-8",
    )

    advisory = FakeAdvisory()
    service = WingmanBriefService(
        advisory,
        docs_root=tmp_path,
    )

    payload = service.brief(
        {
            "system": {
                "hostname": "BattleStation",
                "healthy": True,
            },
            "storage": {
                "pools": [{"name": "HDDs", "health": "ONLINE"}],
            },
            "definitely_not_allowlisted": {
                "secret": "do not forward",
            },
        }
    )

    assert payload["status"] == "EXPLAINED"
    assert payload["advisory_only"] is True
    assert payload["control_authority"] is False
    assert payload["production_mutation"] is False
    assert payload["lifecycle"] == {
        "runtime_started": True,
        "model_invoked": True,
        "runtime_reaped": True,
    }

    assert len(advisory.calls) == 1
    call = advisory.calls[0]

    assert call["question"] == BRIEF_QUESTION

    source_ids = {
        source.source_id
        for source in call["sources"]
    }

    assert "status:system" in source_ids
    assert "status:storage" in source_ids
    assert (
        "manual:MISSION_CONTROL.md:overview"
        in source_ids
    )

    assert not any(
        "definitely_not_allowlisted" in source_id
        for source_id in source_ids
    )
