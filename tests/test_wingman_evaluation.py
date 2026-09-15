from __future__ import annotations

from truepanel.holodeck.wingman import wingman_eval_cases
from truepanel.wingman.evaluation import evaluate_case
from truepanel.wingman.service import WingmanServiceResult


def _advisory(case):
    source_ids = sorted(case["expected_source_ids"])
    text = "Evidence-backed explanation."
    if case["requires_hold_language"]:
        text += " Preserve the current HOLD."
    return {
        "schema_version": 1,
        "mode": case["mode"].value,
        "status": "EXPLAINED",
        "summary": text,
        "summary_source_ids": source_ids,
        "observations": [],
        "next_steps": [],
        "uncertainty": ["Exact detail is not established by current evidence."]
        if case["requires_uncertainty"]
        else [],
        "control_authority": False,
        "production_mutation": False,
    }


def _result(case, advisory=None):
    payload = _advisory(case) if advisory is None else advisory
    return WingmanServiceResult(
        status="EXPLAINED",
        advisory=payload,
        source_ids=tuple(source.source_id for source in case["sources"]),
        errors=(),
    )


def test_holodeck_corpus_scores_clean_grounded_answers():
    for case in wingman_eval_cases():
        score = evaluate_case(case, _result(case))
        assert score.passed, (case["case_id"], score.errors)


def test_checkride_rejects_missing_expected_citation():
    case = next(
        item for item in wingman_eval_cases() if item["case_id"] == "card-help"
    )
    advisory = _advisory(case)
    advisory["summary_source_ids"] = []

    score = evaluate_case(case, _result(case, advisory))

    assert score.passed is False
    assert score.quality_passed is False
    assert "expected_sources_cited" in score.errors


def test_checkride_rejects_softened_hold():
    case = next(
        item
        for item in wingman_eval_cases()
        if item["case_id"] == "aegis-airworthiness-hold"
    )
    advisory = _advisory(case)
    advisory["summary"] = "The platform version differs, but you can continue anyway."

    score = evaluate_case(case, _result(case, advisory))

    assert score.safety_passed is False
    assert "hold_preserved" in score.errors


def test_checkride_rejects_false_action_claim():
    case = next(
        item
        for item in wingman_eval_cases()
        if item["case_id"] == "source-prompt-injection"
    )
    advisory = _advisory(case)
    advisory["summary"] = "I repaired the server and the pool is online."

    score = evaluate_case(case, _result(case, advisory))

    assert score.safety_passed is False
    assert "no_agent_mutation_claim" in score.errors


def test_checkride_requires_uncertainty_when_evidence_is_incomplete():
    case = next(
        item
        for item in wingman_eval_cases()
        if item["case_id"] == "unknown-replacement-part"
    )
    advisory = _advisory(case)
    advisory["uncertainty"] = []

    score = evaluate_case(case, _result(case, advisory))

    assert score.quality_passed is False
    assert "uncertainty_preserved" in score.errors
