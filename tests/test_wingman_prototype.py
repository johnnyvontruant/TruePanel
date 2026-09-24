"""Contract tests for WINGMAN's isolated, operator-started cockpit."""

from __future__ import annotations

from http import HTTPStatus

import pytest

from truepanel.wingman import prototype


def test_non_wingman_post_is_refused_without_delegation(monkeypatch):
    def unexpected_post(self):
        raise AssertionError("mutation endpoint was delegated")

    monkeypatch.setattr(
        prototype.MissionControlRequestHandler, "do_POST", unexpected_post
    )
    handler = object.__new__(prototype.WingmanPrototypeHandler)
    handler.path = "/api/v1/fans/thermal-arm"
    responses = []
    handler._json = lambda payload, status: responses.append((payload, status))

    handler.do_POST()

    assert len(responses) == 1
    payload, status = responses[0]
    assert payload["error"] == "wingman_prototype_read_only"
    assert status == HTTPStatus.FORBIDDEN


def test_only_wingman_brief_post_is_delegated(monkeypatch):
    delegated = []

    def record_post(self):
        delegated.append(self.path)

    monkeypatch.setattr(
        prototype.MissionControlRequestHandler, "do_POST", record_post
    )
    handler = object.__new__(prototype.WingmanPrototypeHandler)
    handler.path = "/api/v1/wingman/brief?request=manual"

    handler.do_POST()

    assert delegated == ["/api/v1/wingman/brief?request=manual"]


def test_prototype_accepts_missing_local_model_for_offline_mode(tmp_path):
    parser = prototype.build_parser()
    args = parser.parse_args(
        [
            "--llama-server", str(tmp_path / "missing-llama-server"),
            "--model", str(tmp_path / "missing-model.gguf"),
            "--docs-root", str(tmp_path),
        ]
    )
    prototype.validate_options(args, parser)
    service = prototype.build_brief_service(
        llama_server=args.llama_server,
        model=args.model,
        docs_root=args.docs_root,
    )
    assert service.advisory.runtime.running is False
    from truepanel.wingman.readiness import (
        file_availability, inference_readiness,
    )
    from truepanel.wingman.runtime import HostResources

    report = inference_readiness(
        HostResources(available_memory_bytes=4 * 1024**3, load_1m=1.0),
        file_availability(args.llama_server, args.model),
    )
    assert report["status"] == "HOLD"
    assert set(report["reason_codes"]) == {
        "LLAMA_SERVER_MISSING", "MODEL_FILE_MISSING",
    }


def test_production_port_is_rejected_even_with_valid_resources(tmp_path):
    server_path = tmp_path / "llama-server"
    model_path = tmp_path / "model.gguf"
    server_path.touch()
    model_path.touch()

    parser = prototype.build_parser()
    args = parser.parse_args(
        [
            "--llama-server", str(server_path),
            "--model", str(model_path),
            "--docs-root", str(tmp_path),
            "--port", "8787",
        ]
    )
    with pytest.raises(SystemExit) as error:
        prototype.validate_options(args, parser)
    assert error.value.code == 2


def test_prototype_is_loopback_and_disables_configuration_writes(
    tmp_path, monkeypatch
):
    server_path = tmp_path / "llama-server"
    model_path = tmp_path / "model.gguf"
    server_path.touch()
    model_path.touch()
    recorded = {}

    class FakeServer:
        def __init__(self, address, **kwargs):
            recorded["address"] = address
            recorded["options"] = kwargs

        def serve_forever(self):
            recorded["served"] = True

        def server_close(self):
            recorded["closed"] = True

    monkeypatch.setattr(prototype, "MissionControlServer", FakeServer)

    prototype.main(
        [
            "--llama-server", str(server_path),
            "--model", str(model_path),
            "--docs-root", str(tmp_path),
        ]
    )

    assert recorded["address"] == ("127.0.0.1", 18787)
    assert recorded["options"]["allow_config_writes"] is False
    assert recorded["served"] is True
    assert recorded["closed"] is True

    brief = recorded["options"]["wingman_brief_service"]
    assert brief.docs_root == tmp_path
    assert brief.advisory.runtime.config.server_path == server_path
    assert brief.advisory.runtime.config.model_path == model_path
    assert brief.advisory.runtime.running is False


def test_prototype_always_closes_its_listener(tmp_path, monkeypatch):
    server_path = tmp_path / "llama-server"
    model_path = tmp_path / "model.gguf"
    server_path.touch()
    model_path.touch()
    recorded = {}

    class FakeServer:
        def __init__(self, address, **kwargs):
            pass

        def serve_forever(self):
            raise RuntimeError("listener interrupted")

        def server_close(self):
            recorded["closed"] = True

    monkeypatch.setattr(prototype, "MissionControlServer", FakeServer)

    with pytest.raises(RuntimeError, match="listener interrupted"):
        prototype.main(
            [
                "--llama-server", str(server_path),
                "--model", str(model_path),
                "--docs-root", str(tmp_path),
            ]
        )

    assert recorded["closed"] is True


def test_prototype_can_start_offline_without_any_model_arguments(monkeypatch):
    result = {}

    class FakeServer:
        def __init__(self, address, **kwargs):
            result["address"] = address
            result["service"] = kwargs["wingman_brief_service"]
        def serve_forever(self):
            result["served"] = True
        def server_close(self):
            result["closed"] = True

    monkeypatch.setattr(prototype, "MissionControlServer", FakeServer)
    prototype.main([])
    assert result["address"] == ("127.0.0.1", prototype.PROTOTYPE_PORT)
    assert result["served"] is True
    assert result["closed"] is True
    assert result["service"].advisory.runtime.running is False
    assert not result["service"].advisory.runtime.config.model_path.is_file()
