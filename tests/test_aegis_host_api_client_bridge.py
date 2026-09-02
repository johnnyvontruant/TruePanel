import pytest

from truepanel.aegis import _truenas_api_client_helper as helper
from truepanel.aegis import passive_websocket as websocket
from truepanel.aegis.passive_providers import PASSIVE_METHODS


def test_default_factory_prefers_in_environment_client(monkeypatch):
    captured = []

    class DirectClient:
        def __init__(self, **kwargs):
            captured.append(kwargs)

    monkeypatch.setattr(
        websocket,
        "_import_truenas_client_class",
        lambda: DirectClient,
    )

    client = websocket.TrueNASWebSocketReadOnlyClient._default_client_factory(
        uri="wss://localhost/api/current",
        verify_ssl=True,
        call_timeout=10.0,
    )

    assert isinstance(client, DirectClient)
    assert captured == [
        {
            "uri": "wss://localhost/api/current",
            "verify_ssl": True,
            "call_timeout": 10.0,
        }
    ]


def test_default_factory_falls_back_to_governed_host_helper(monkeypatch):
    captured = []

    class HostBridge:
        def __init__(self, **kwargs):
            captured.append(kwargs)

    monkeypatch.setattr(
        websocket,
        "_import_truenas_client_class",
        lambda: None,
    )
    monkeypatch.setattr(websocket, "_HostPythonClientProxy", HostBridge)

    client = websocket.TrueNASWebSocketReadOnlyClient._default_client_factory(
        uri="wss://localhost/api/current",
        verify_ssl=True,
        call_timeout=10.0,
    )

    assert isinstance(client, HostBridge)
    assert captured == [
        {
            "uri": "wss://localhost/api/current",
            "verify_ssl": True,
            "call_timeout": 10.0,
        }
    ]


def test_host_helper_environment_does_not_inherit_arbitrary_secrets(monkeypatch):
    monkeypatch.setenv("TRUEPANEL_FAKE_SECRET", "do-not-inherit")
    monkeypatch.setenv("SSL_CERT_FILE", "/governed/ca.pem")

    environment = websocket._host_helper_environment()

    assert environment == {
        "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
        "PYTHONNOUSERSITE": "1",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "SSL_CERT_FILE": "/governed/ca.pem",
    }
    assert "TRUEPANEL_FAKE_SECRET" not in environment


def test_host_helper_duplicates_only_the_passive_call_boundary():
    assert helper.ALLOWED_CALL_METHODS == set(PASSIVE_METHODS) | {"auth.login_ex"}
    assert "system.shutdown" not in helper.ALLOWED_CALL_METHODS
    assert "replication.run" not in helper.ALLOWED_CALL_METHODS
    assert "replication.create" not in helper.ALLOWED_CALL_METHODS


def test_host_helper_rejects_unsafe_open_requests():
    assert (
        helper._valid_open_request(
            {
                "uri": "ws://localhost/api/current",
                "verify_ssl": True,
                "call_timeout": 10,
            }
        )
        is None
    )
    assert (
        helper._valid_open_request(
            {
                "uri": "wss://user:secret@localhost/api/current",
                "verify_ssl": True,
                "call_timeout": 10,
            }
        )
        is None
    )
    assert (
        helper._valid_open_request(
            {
                "uri": "wss://localhost/api/current",
                "verify_ssl": False,
                "call_timeout": 10,
            }
        )
        is None
    )
    assert helper._valid_open_request(
        {
            "uri": "wss://localhost/api/current",
            "verify_ssl": True,
            "call_timeout": 10,
        }
    ) == ("wss://localhost/api/current", 10.0)


def test_host_proxy_blocks_mutating_method_before_pipe_use():
    proxy = object.__new__(websocket._HostPythonClientProxy)

    with pytest.raises(ValueError, match="not passive allowlisted"):
        proxy.call("system.shutdown")
