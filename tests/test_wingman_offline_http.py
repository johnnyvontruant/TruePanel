"""HoloDeck-style HTTP contract checks for model-free prototype GET routes."""

from __future__ import annotations

from types import SimpleNamespace

from truepanel.wingman import prototype
from truepanel.wingman.runtime import (
    HostResources,
    LlamaRuntimeConfig,
    RuntimePolicy,
)

GIB = 1024**3


def handler_for(path, snapshot, runtime):
    handler = object.__new__(prototype.WingmanPrototypeHandler)
    handler.path = path
    handler.snapshot_service = SimpleNamespace(status=lambda: snapshot)
    handler.server = SimpleNamespace(
        wingman_brief_service=SimpleNamespace(
            advisory=SimpleNamespace(runtime=runtime)
        )
    )
    responses = []
    handler._json = lambda payload, **kwargs: responses.append(payload)
    return handler, responses


def test_offline_get_is_model_free_and_cites_snapshot():
    runtime = SimpleNamespace(
        _resource_reader=lambda: (_ for _ in ()).throw(
            AssertionError("readiness not requested")
        )
    )
    handler, responses = handler_for(
        "/api/v1/wingman/offline-brief",
        {"storage": {"pools": [{"name": "SSDs", "health": "ONLINE"}]}},
        runtime,
    )
    handler.do_GET()
    assert len(responses) == 1
    assert responses[0]["status"] == "OBSERVED"
    assert responses[0]["model_invoked"] is False
    assert responses[0]["source_ids"] == ["status:storage"]


def test_readiness_get_does_not_start_model(tmp_path):
    server = tmp_path / "llama-server"
    model = tmp_path / "model.gguf"
    server.touch()
    model.touch()
    runtime = SimpleNamespace(
        config=LlamaRuntimeConfig(server_path=server, model_path=model),
        policy=RuntimePolicy(),
        _resource_reader=lambda: HostResources(
            available_memory_bytes=GIB, load_1m=4.63
        ),
        start=lambda: (_ for _ in ()).throw(
            AssertionError("readiness started a model")
        ),
    )
    handler, responses = handler_for(
        "/api/v1/wingman/readiness", {}, runtime
    )
    handler.do_GET()
    assert len(responses) == 1
    assert responses[0]["reason_codes"] == ["MEMORY_BELOW_POLICY"]
    assert responses[0]["model_invoked"] is False
    assert responses[0]["launch_authorized"] is False


def test_readiness_get_fails_closed_when_resource_reader_raises(tmp_path):
    runtime = SimpleNamespace(
        config=LlamaRuntimeConfig(
            server_path=tmp_path / "missing-server",
            model_path=tmp_path / "missing-model",
        ),
        policy=RuntimePolicy(),
        _resource_reader=lambda: (_ for _ in ()).throw(
            OSError("host reading unavailable")
        ),
    )
    handler, responses = handler_for(
        "/api/v1/wingman/readiness", {}, runtime
    )
    handler.do_GET()
    assert responses[0]["status"] == "HOLD"
    assert "HOST_RESOURCES_UNAVAILABLE" in responses[0]["reason_codes"]
    assert "MODEL_FILE_MISSING" in responses[0]["reason_codes"]
