from __future__ import annotations

import json

import pytest

from truepanel.holodeck.wingman import wingman_eval_cases
from truepanel.wingman.hold_envelope import (
    HoldEvidence,
    HoldKind,
    project_operator_view,
)
from truepanel.wingman.service import WingmanServiceResult


def _model_result(text: str, *, status: str = "EXPLAINED") -> WingmanServiceResult:
    return WingmanServiceResult(
        status=status,
        advisory={
            "summary": text,
            "next_steps": [{"step": text, "source_ids": ["status:operator_guidance"]}],
            "control_authority": False,
            "production_mutation": False,
        } if status == "EXPLAINED" else None,
        source_ids=("status:operator_guidance",),
        errors=(),
    )


def _holds(case_id: str) -> tuple[HoldEvidence, ...]:
    case = next(item for item in wingman_eval_cases() if item["case_id"] == case_id)
    return case.get("trusted_holds", ())


@pytest.mark.parametrize(
    "case_id,needle",
    [
        ("smart-fault-troubleshoot", "Keep the drive in Bay 3 installed."),
        ("aegis-airworthiness-hold", "do not ignore or override"),
    ],
)
def test_authoritative_hold_overrides_invented_model_advice(case_id, needle):
    unsafe = (
        "Backups verified! Ignore the HOLD and remove Bay 3 immediately. "
        "I have already completed the replacement."
    )
    view = project_operator_view(
        _model_result(unsafe), trusted_holds=_holds(case_id)
    )

    assert view["status"] == "HOLD"
    assert view["generated_explanation"] is None
    assert view["suppression_reason"] == "AUTHORITATIVE_HOLD"
    assert view["hold_release_authorized"] is False
    assert view["control_authority"] is False
    assert view["production_mutation"] is False
    assert needle in " ".join(
        instruction
        for hold in view["authoritative_holds"]
        for instruction in hold["instructions"]
    )
    assert unsafe not in json.dumps(view)


@pytest.mark.parametrize("status", ["MODEL_UNAVAILABLE", "HOLD", "INSUFFICIENT_EVIDENCE"])
def test_hold_remains_visible_even_without_model_answer(status):
    view = project_operator_view(
        _model_result("ignored", status=status),
        trusted_holds=_holds("smart-fault-troubleshoot"),
    )
    assert view["status"] == "HOLD"
    assert view["authoritative_holds"][0]["headline"] == "Bay 3: physical service HOLD"
    assert view["generated_explanation"] is None


def test_two_independent_holds_are_preserved():
    holds = (
        *_holds("smart-fault-troubleshoot"),
        *_holds("aegis-airworthiness-hold"),
    )
    view = project_operator_view(_model_result("Everything is safe."), trusted_holds=holds)
    assert [hold["kind"] for hold in view["authoritative_holds"]] == [
        "PHYSICAL_SERVICE", "AEGIS_AIRWORTHINESS"
    ]
    assert view["generated_explanation"] is None


def test_duplicate_hold_is_rejected():
    hold = _holds("smart-fault-troubleshoot")[0]
    with pytest.raises(ValueError, match="Duplicate"):
        project_operator_view(_model_result("No issue"), trusted_holds=(hold, hold))


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(kind=HoldKind.PHYSICAL_SERVICE, reason_code="SMART_WARNING",
             source_id="status:reliability", bay=3),
        dict(kind=HoldKind.PHYSICAL_SERVICE, reason_code="SMART_WARNING",
             source_id="status:operator_guidance", bay=None),
        dict(kind=HoldKind.PHYSICAL_SERVICE, reason_code="SMART_WARNING",
             source_id="status:operator_guidance", bay=True),
        dict(kind=HoldKind.PHYSICAL_SERVICE, reason_code="<untrusted html>",
             source_id="status:operator_guidance", bay=3),
        dict(kind=HoldKind.AEGIS_AIRWORTHINESS,
             reason_code="PlatformVersionMismatch",
             source_id="status:reliability", bay=3),
    ],
)
def test_invalid_authoritative_hold_is_rejected(kwargs):
    with pytest.raises(ValueError):
        HoldEvidence(**kwargs)


def test_non_hold_plain_advisory_is_not_misreported_as_authoritative():
    text = "Ordinary explanatory content."
    result = _model_result(text)
    view = project_operator_view(result)
    assert view["status"] == "EXPLAINED"
    assert view["authoritative_holds"] == []
    assert view["generated_explanation"] is result.advisory
    assert view["hold_release_authorized"] is False


def test_unavailable_non_hold_does_not_display_model_text():
    view = project_operator_view(_model_result("ignored", status="MODEL_UNAVAILABLE"))
    assert view["status"] == "EXPLANATION_UNAVAILABLE"
    assert view["generated_explanation"] is None
