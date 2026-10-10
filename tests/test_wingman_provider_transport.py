"""Exercise endpoint custody with real HTTP peers and synthetic evidence."""

import json
import threading
import urllib.request
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError

import pytest

from truepanel.wingman.contracts import GroundingSource, WingmanMode
from truepanel.wingman.provider import LlamaCppProvider
from truepanel.wingman.service import WingmanAdvisoryService


@contextmanager
def peer(*, status=200, location=None):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            calls.append((self.command, self.path, body))
            self.send_response(status)
            if location is not None:
                self.send_header("Location", location)
            self.end_headers()
            if status == 200:
                self.wfile.write(json.dumps({
                    "choices": [{"message": {"content": '{"summary":"synthetic"}'}}],
                }).encode())

        def do_GET(self):
            calls.append((self.command, self.path, b""))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def complete(provider):
    return provider.complete(
        system_prompt="Synthetic policy",
        user_prompt="Synthetic evidence",
        response_schema={"type": "object"},
    )


def test_direct_completion_preserves_request_contract():
    with peer() as (url, calls):
        provider = LlamaCppProvider(endpoint=url + "/v1/chat/completions")
        assert complete(provider) == {"summary": "synthetic"}
        assert len(calls) == 1
        method, path, body = calls[0]
        assert (method, path) == ("POST", "/v1/chat/completions")
        payload = json.loads(body)
        assert payload["messages"][1]["content"] == "Synthetic evidence"
        assert payload["stream"] is False
        assert payload["max_tokens"] == 900
        assert payload["response_format"]["schema"] == {"type": "object"}


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
@pytest.mark.parametrize("relative", [False, True])
def test_redirects_never_contact_another_endpoint(status, relative):
    with peer() as (target, target_calls):
        location = "/redirected" if relative else target + "/redirected"
        with peer(status=status, location=location) as (url, calls):
            provider = LlamaCppProvider(endpoint=url + "/v1/chat/completions")
            with pytest.raises(HTTPError) as caught:
                complete(provider)
            assert caught.value.code == status
            caught.value.close()
            assert len(calls) == 1
            assert calls[0][1] == "/v1/chat/completions"
            assert target_calls == []


@pytest.mark.parametrize("allow_remote", [False, True])
def test_ambient_proxy_never_receives_model_evidence(monkeypatch, allow_remote):
    with peer() as (proxy, proxy_calls), peer() as (url, calls):
        for name in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
            monkeypatch.setenv(name, proxy)
        monkeypatch.setenv("no_proxy", "")
        monkeypatch.setenv("NO_PROXY", "")
        provider = LlamaCppProvider(
            endpoint=url + "/v1/chat/completions", allow_remote=allow_remote,
        )
        assert complete(provider) == {"summary": "synthetic"}
        assert len(calls) == 1
        assert proxy_calls == []


def test_process_global_opener_cannot_intercept_request(monkeypatch):
    class ForeignOpener:
        def open(self, *args, **kwargs):
            pytest.fail("WINGMAN used the process-global opener")

    monkeypatch.setattr(urllib.request, "_opener", ForeignOpener())
    with peer() as (url, calls):
        assert complete(LlamaCppProvider(endpoint=url)) == {"summary": "synthetic"}
        assert len(calls) == 1


def test_redirect_becomes_model_unavailable_without_authority():
    with peer(status=302, location="/redirected") as (url, calls):
        service = WingmanAdvisoryService(LlamaCppProvider(endpoint=url))
        result = service.advise(
            mode=WingmanMode.BRIEF,
            question="system status",
            sources=(GroundingSource(
                source_id="status:system", kind="mission_control_status",
                title="System status", content="system status healthy",
            ),),
        )
        assert result.status == "MODEL_UNAVAILABLE"
        assert result.advisory is None
        assert result.control_authority is False
        assert result.production_mutation is False
        assert len(calls) == 1
