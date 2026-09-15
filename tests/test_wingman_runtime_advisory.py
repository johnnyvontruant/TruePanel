from __future__ import annotations

from dataclasses import dataclass

from truepanel.wingman.contracts import GroundingSource, WingmanMode
from truepanel.wingman.runtime_advisory import WingmanRuntimeAdvisory

SOURCE = GroundingSource(
    source_id="status:test",
    kind="mission_control_status",
    title="Test",
    content="system healthy",
)


class FakeRuntime:
    def __init__(
        self,
        *,
        fail_start: Exception | None = None,
    ) -> None:
        self.fail_start = fail_start
        self.running = False
        self.start_calls = 0
        self.stop_calls = 0

    @property
    def endpoint(self) -> str:
        if not self.running:
            raise RuntimeError("stopped")
        return "http://127.0.0.1:18080/v1/chat/completions"

    def start(self) -> str:
        self.start_calls += 1

        if self.fail_start is not None:
            raise self.fail_start

        self.running = True
        return self.endpoint

    def stop(self) -> None:
        self.stop_calls += 1
        self.running = False


@dataclass
class FakeProvider:
    answer: dict | None = None
    error: Exception | None = None
    calls: int = 0

    def complete(
        self,
        *,
        system_prompt,
        user_prompt,
        response_schema,
    ):
        self.calls += 1

        if self.error is not None:
            raise self.error

        return self.answer


def valid_answer():
    return {
        "schema_version": 1,
        "mode": "brief",
        "status": "EXPLAINED",
        "summary": "System healthy.",
        "summary_source_ids": ["status:test"],
        "observations": [
            {
                "text": "System healthy.",
                "source_ids": ["status:test"],
            }
        ],
        "next_steps": [],
        "uncertainty": [],
        "control_authority": False,
        "production_mutation": False,
    }


def test_success_always_stops_runtime():
    runtime = FakeRuntime()
    provider = FakeProvider(answer=valid_answer())

    advisory = WingmanRuntimeAdvisory(
        runtime,
        provider_factory=lambda endpoint: provider,
    )

    result, observation = advisory.advise(
        mode=WingmanMode.BRIEF,
        question="How is the system?",
        sources=(SOURCE,),
    )

    assert result.status == "EXPLAINED"
    assert observation.runtime_started is True
    assert observation.model_invoked is True
    assert observation.runtime_reaped is True
    assert runtime.start_calls == 1
    assert runtime.stop_calls == 1
    assert runtime.running is False


def test_model_failure_still_stops_runtime():
    runtime = FakeRuntime()
    provider = FakeProvider(error=RuntimeError("model failed"))

    advisory = WingmanRuntimeAdvisory(
        runtime,
        provider_factory=lambda endpoint: provider,
    )

    result, observation = advisory.advise(
        mode=WingmanMode.BRIEF,
        question="How is the system?",
        sources=(SOURCE,),
    )

    assert result.status == "MODEL_UNAVAILABLE"
    assert observation.runtime_started is True
    assert observation.model_invoked is True
    assert runtime.stop_calls == 1
    assert runtime.running is False


def test_resource_or_startup_hold_does_not_invoke_model():
    runtime = FakeRuntime(
        fail_start=RuntimeError("resource hold"),
    )
    provider = FakeProvider(answer=valid_answer())

    advisory = WingmanRuntimeAdvisory(
        runtime,
        provider_factory=lambda endpoint: provider,
    )

    result, observation = advisory.advise(
        mode=WingmanMode.BRIEF,
        question="How is the system?",
        sources=(SOURCE,),
    )

    assert result.status == "MODEL_UNAVAILABLE"
    assert observation.runtime_started is False
    assert observation.model_invoked is False
    assert observation.runtime_reaped is True
    assert provider.calls == 0
    assert runtime.running is False


def test_second_concurrent_request_fails_closed():
    runtime = FakeRuntime()
    provider = FakeProvider(answer=valid_answer())

    advisory = WingmanRuntimeAdvisory(
        runtime,
        provider_factory=lambda endpoint: provider,
    )

    advisory._lock.acquire()

    try:
        result, observation = advisory.advise(
            mode=WingmanMode.BRIEF,
            question="How is the system?",
            sources=(SOURCE,),
        )
    finally:
        advisory._lock.release()

    assert result.status == "MODEL_UNAVAILABLE"
    assert result.errors == ("InferenceBusy",)
    assert observation.runtime_started is False
    assert observation.model_invoked is False
    assert runtime.start_calls == 0


def test_invalid_grounding_result_still_reaps_runtime():
    runtime = FakeRuntime()

    invalid = valid_answer()
    invalid["summary_source_ids"] = ["invented:source"]

    provider = FakeProvider(answer=invalid)

    advisory = WingmanRuntimeAdvisory(
        runtime,
        provider_factory=lambda endpoint: provider,
    )

    result, _observation = advisory.advise(
        mode=WingmanMode.BRIEF,
        question="How is the system?",
        sources=(SOURCE,),
    )

    assert result.status == "HOLD"
    assert runtime.stop_calls == 1
    assert runtime.running is False


def test_default_runtime_provider_uses_bounded_brief_contract():
    from truepanel.wingman.provider import LlamaCppProvider
    from truepanel.wingman.runtime_advisory import (
        WingmanRuntimeAdvisory,
    )

    provider = WingmanRuntimeAdvisory._default_provider(
        "http://127.0.0.1:18080/v1/chat/completions"
    )

    assert isinstance(provider, LlamaCppProvider)
    assert provider.timeout_seconds == 60.0
    assert provider.max_tokens == 512
    assert provider.allow_remote is False
