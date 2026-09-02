import json
import os

import pytest

from truepanel.aegis.passive_observation import observe_websocket
from truepanel.aegis.passive_runtime import REQUIRED_ROLES
from truepanel.aegis.passive_websocket import (
    GovernedAPIKeyFile,
    GovernedTLSCAFile,
    TRANSPORT_BOOTSTRAP_METHODS,
    TrueNASWebSocketReadOnlyClient,
)


API_KEY = "k" * 64


def write_key(tmp_path, *, mode=0o600):
    path = tmp_path / "aegis-api-key"
    path.write_text(API_KEY)
    path.chmod(mode)
    return path


def write_ca(tmp_path, *, mode=0o600, private=False):
    path = tmp_path / "truenas-local-cert.pem"
    body = (
        "-----BEGIN PRIVATE KEY-----\nforbidden\n-----END PRIVATE KEY-----\n"
        if private
        else "-----BEGIN CERTIFICATE-----\nZmFrZQ==\n-----END CERTIFICATE-----\n"
    )
    path.write_text(body)
    path.chmod(mode)
    return path


class FakeClient:
    def __init__(self, responses, *, login_success=True):
        self.responses = responses
        self.login_success = login_success
        self.calls = []
        self.closed = False

    def call(self, method, *arguments):
        self.calls.append((method, arguments))
        if method == "auth.login_ex":
            return {"response_type": "SUCCESS" if self.login_success else "AUTH_ERR"}
        return self.responses.get(method)

    def close(self):
        self.closed = True


def factory_for(fake, captured):
    def factory(**kwargs):
        captured.append(kwargs)
        return fake

    return factory


def identity(*roles):
    return {
        "local": True,
        "pw_name": "service-account-must-not-be-published",
        "privilege": {"roles": list(roles)},
    }


def test_websocket_transport_requires_tls_verified_current_endpoint(tmp_path):
    key = write_key(tmp_path)
    with pytest.raises(ValueError, match="requires wss"):
        TrueNASWebSocketReadOnlyClient(
            uri="ws://nas.example/api/current",
            username="truepanel-aegis",
            api_key_file=key,
        )
    with pytest.raises(ValueError, match="credentials must not be embedded"):
        TrueNASWebSocketReadOnlyClient(
            uri="wss://user:secret@nas.example/api/current",
            username="truepanel-aegis",
            api_key_file=key,
        )
    with pytest.raises(ValueError, match="/api/current"):
        TrueNASWebSocketReadOnlyClient(
            uri="wss://nas.example/websocket",
            username="truepanel-aegis",
            api_key_file=key,
        )


def test_api_key_file_requires_owner_only_regular_file(tmp_path):
    key = write_key(tmp_path, mode=0o640)
    status = GovernedAPIKeyFile(key).status()
    assert status["governed"] is False
    assert GovernedAPIKeyFile(key).load() is None

    key.chmod(0o600)
    link = tmp_path / "linked-key"
    link.symlink_to(key)
    assert GovernedAPIKeyFile(link).status()["governed"] is False
    assert GovernedAPIKeyFile(link).load() is None


def test_tls_ca_file_rejects_mutable_symlink_or_private_material(tmp_path):
    ca = write_ca(tmp_path, mode=0o666)
    assert GovernedTLSCAFile(ca).status()["governed"] is False

    ca.chmod(0o600)
    link = tmp_path / "linked-ca"
    link.symlink_to(ca)
    assert GovernedTLSCAFile(link).status()["governed"] is False

    ca.write_text("-----BEGIN PRIVATE KEY-----\nforbidden\n-----END PRIVATE KEY-----\n")
    ca.chmod(0o600)
    status = GovernedTLSCAFile(ca).status()
    assert status["governed"] is False
    assert "private key" in status["reason"]


def test_websocket_client_authenticates_once_and_keeps_key_out_of_argv_surface(tmp_path):
    key = write_key(tmp_path)
    fake = FakeClient(
        {
            "auth.me": identity(*REQUIRED_ROLES),
            "replication.query": [],
            "cloud_backup.query": [],
        }
    )
    captured = []
    client = TrueNASWebSocketReadOnlyClient(
        uri="wss://nas.example/api/current",
        username="truepanel-aegis",
        api_key_file=key,
        client_factory=factory_for(fake, captured),
    )

    assert client.call("auth.me")["privilege"]["roles"]
    assert client.call("replication.query", [], {}) == []
    assert client.call("cloud_backup.query", [], {}) == []
    assert [call[0] for call in fake.calls].count("auth.login_ex") == 1
    assert captured == [
        {
            "uri": "wss://nas.example/api/current",
            "verify_ssl": True,
            "call_timeout": 10.0,
        }
    ]
    login_payload = fake.calls[0][1][0]
    assert login_payload["mechanism"] == "API_KEY_PLAIN"
    assert login_payload["api_key"] == API_KEY
    assert login_payload["login_options"] == {"user_info": False}
    status = client.status()
    assert status["credential"]["secret_in_argv_allowed"] is False
    assert status["credential"]["path_published"] is False
    assert status["username_published"] is False
    assert status["uri_published"] is False
    assert status["transport_bootstrap"]["methods"] == list(TRANSPORT_BOOTSTRAP_METHODS)
    assert status["transport_bootstrap"]["core_set_options_scope"] == "connection_only"
    assert status["transport_bootstrap"]["persistent_configuration_changed"] is False


def test_process_local_ca_is_applied_only_during_client_connection(tmp_path, monkeypatch):
    key = write_key(tmp_path)
    ca = write_ca(tmp_path)
    fake = FakeClient({"auth.me": identity(*REQUIRED_ROLES)})
    observed = []
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)

    def factory(**_kwargs):
        observed.append(os.environ.get("SSL_CERT_FILE"))
        return fake

    client = TrueNASWebSocketReadOnlyClient(
        uri="wss://localhost/api/current",
        username="truepanel-aegis",
        api_key_file=key,
        tls_ca_file=ca,
        client_factory=factory,
    )
    assert client.call("auth.me")["privilege"]["roles"]
    assert observed == [str(ca)]
    assert "SSL_CERT_FILE" not in os.environ
    status = client.status()["tls_trust"]
    assert status["governed"] is True
    assert status["source"] == "process_local_ca_file"
    assert status["system_trust_store_changed"] is False
    assert status["path_published"] is False


def test_invalid_tls_ca_fails_closed_before_client_connection(tmp_path):
    key = write_key(tmp_path)
    ca = write_ca(tmp_path, private=True)
    fake = FakeClient({"auth.me": identity(*REQUIRED_ROLES)})
    captured = []
    client = TrueNASWebSocketReadOnlyClient(
        uri="wss://localhost/api/current",
        username="truepanel-aegis",
        api_key_file=key,
        tls_ca_file=ca,
        client_factory=factory_for(fake, captured),
    )
    assert client.call("auth.me") is None
    assert captured == []
    assert fake.calls == []


def test_websocket_client_blocks_non_passive_methods_before_connecting(tmp_path):
    key = write_key(tmp_path)
    fake = FakeClient({})
    captured = []
    client = TrueNASWebSocketReadOnlyClient(
        uri="wss://nas.example/api/current",
        username="truepanel-aegis",
        api_key_file=key,
        client_factory=factory_for(fake, captured),
    )
    with pytest.raises(ValueError, match="not passive allowlisted"):
        client.call("system.shutdown")
    assert captured == []
    assert fake.calls == []


def test_authentication_failure_fails_closed_without_querying_data(tmp_path):
    key = write_key(tmp_path)
    fake = FakeClient({"auth.me": identity(*REQUIRED_ROLES)}, login_success=False)
    client = TrueNASWebSocketReadOnlyClient(
        uri="wss://nas.example/api/current",
        username="truepanel-aegis",
        api_key_file=key,
        client_factory=lambda **_kwargs: fake,
    )
    assert client.call("auth.me") is None
    assert [call[0] for call in fake.calls] == ["auth.login_ex"]
    assert fake.closed is True
    assert client.status()["authenticated"] is False


def test_no_deploy_websocket_observation_is_sanitized_and_closes_session(tmp_path):
    key = write_key(tmp_path)
    ca = write_ca(tmp_path)
    receipt_root = tmp_path / "receipts"
    receipt_root.mkdir(mode=0o700)
    fake = FakeClient(
        {
            "auth.me": identity(*REQUIRED_ROLES),
            "replication.query": [],
            "cloud_backup.query": [],
        }
    )
    result = observe_websocket(
        "incident-1",
        receipt_root,
        uri="wss://nas.example/api/current",
        username="truepanel-aegis",
        api_key_file=key,
        tls_ca_file=ca,
        client_factory=lambda **_kwargs: fake,
    )

    assert result["operation"] == "passive_no_deploy_observation"
    assert result["runtime_status"] == "HOLD"
    assert result["role_verification"]["least_privilege_verified"] is True
    assert result["cache"]["delegate_calls"] == 3
    assert result["transport"]["authenticated"] is True
    assert result["transport"]["tls_verification"] is True
    assert result["transport"]["tls_trust"]["governed"] is True
    assert result["control_authority"] is False
    assert result["deployment_changed"] is False
    assert fake.closed is True

    published = json.dumps(result, sort_keys=True)
    assert API_KEY not in published
    assert "truepanel-aegis" not in published
    assert "nas.example" not in published
    assert str(key) not in published
    assert str(ca) not in published
    assert "service-account-must-not-be-published" not in published
