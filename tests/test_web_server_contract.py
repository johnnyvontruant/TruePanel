from pathlib import Path

from truepanel.web.server import MissionControlRequestHandler


def test_server_supports_get():
    assert hasattr(MissionControlRequestHandler, "do_GET")


def test_server_blocks_write_methods():
    assert hasattr(MissionControlRequestHandler, "do_POST")
    assert hasattr(MissionControlRequestHandler, "do_DELETE")


def test_server_defaults_to_localhost():
    source = Path("truepanel/web/server.py").read_text(encoding="utf-8")
    assert 'host="127.0.0.1"' in source
    assert 'default="127.0.0.1"' in source


def test_write_requests_are_read_only():
    source = Path("truepanel/web/server.py").read_text(encoding="utf-8")
    assert '"error": "read_only"' in source
    assert "HTTPStatus.METHOD_NOT_ALLOWED" in source
