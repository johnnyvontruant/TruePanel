import hashlib
import json

import pytest

from truepanel.aegis.authenticated_observation import observe_authenticated
from truepanel.aegis.credential_session import (
    CredentialSafeTrueNASClient,
    PrivateApiKeyFile,
    validate_api_uri,
)
from truepanel.aegis.passive_providers import issue_restore_verification_receipt
from truepanel.aegis.passive_runtime import REQUIRED_ROLES

SECRET = "91-HOLODECK-API-KEY-MATERIAL"


class FakeApiClient:
    def __init__(self, *, authenticated=True, failure=None, roles=None, **kwargs):
        self.authenticated = authenticated
        self.failure = failure
        self.roles = roles or sorted(REQUIRED_ROLES)
        self.kwargs = kwargs
        self.calls = []
        self.closed = False

    def call(self, method, *arguments):
        self.calls.append((method, arguments))
        if self.failure:
            raise RuntimeError(f"upstream failure containing {self.failure}")
        if method == "auth.login_with_api_key":
            return self.authenticated
        if method == "auth.me":
            return {
                "pw_name": "not-published",
                "local": True,
                "privilege": {"roles": self.roles},
            }
        if method == "replication.query":
            return [
                {
                    "id": 7,
                    "enabled": True,
                    "source_datasets": ["HDDs/media"],
                    "state": {"state": "SUCCESS"},
                }
            ]
        if method == "cloud_backup.query":
            return []
        if method == "disk.query":
            return []
        raise AssertionError(f"unexpected method {method}")

    def close(self):
        self.closed = True


class Factory:
    def __init__(self, **client_options):
        self.client_options = client_options
        self.instances = []
        self.kwargs = []

    def __call__(self, **kwargs):
        self.kwargs.append(kwargs)
        client = FakeApiClient(**self.client_options, **kwargs)
        self.instances.append(client)
        return client


def key_file(tmp_path, *, mode=0o600, value=SECRET):
    path = tmp_path / "api.key"
    path.write_text(value)
    path.chmod(mode)
    return path


def receipt_store(tmp_path):
    root = tmp_path / "receipts"
    root.mkdir(mode=0o700, exist_ok=True)
    receipt = issue_restore_verification_receipt(
        incident_id="incident-1",
        method="replication.query",
        task_id=7,
        scope="HDDs/media",
        restore_test_id="restore-42",
        verified_at=990.0,
        objects_verified=12,
    )
    name = hashlib.sha256(b"incident-1").hexdigest() + ".json"
    path = root / name
    path.write_text(json.dumps(receipt))
    path.chmod(0o600)
    return root


@pytest.mark.parametrize(
    "uri",
    [
        "ws://nas.example/api/current",
        "http://nas.example/api/current",
        "wss://user:key@nas.example/api/current",
        "wss://nas.example/websocket",
        "wss://nas.example/api/current?key=secret",
        "wss:///api/current",
    ],
)
def test_api_uri_rejects_downgrade_credentials_and_wrong_endpoint(uri):
    with pytest.raises(ValueError, match="must be wss"):
        validate_api_uri(uri)
    assert validate_api_uri("wss://nas.example:8443/api/current")


def test_private_key_file_requires_absolute_owner_only_regular_file(tmp_path):
    secure = PrivateApiKeyFile(key_file(tmp_path))
    assert secure.status()["secure"] is True
    assert secure.read() == SECRET
    assert SECRET not in json.dumps(secure.status())

    open_file = PrivateApiKeyFile(key_file(tmp_path, mode=0o640))
    assert open_file.status()["secure"] is False
    with pytest.raises(RuntimeError, match="session unavailable"):
        open_file.read()

    relative = PrivateApiKeyFile("relative.key")
    assert relative.status()["secure"] is False


def test_private_key_file_rejects_symlink_oversize_and_whitespace(tmp_path):
    target = key_file(tmp_path)
    link = tmp_path / "link.key"
    link.symlink_to(target)
    assert PrivateApiKeyFile(link).status()["secure"] is False

    target.write_text("x" * 4097)
    assert PrivateApiKeyFile(target).status()["secure"] is False

    target.write_text("key with spaces")
    target.chmod(0o600)
    with pytest.raises(RuntimeError, match="session unavailable"):
        PrivateApiKeyFile(target).read()


def test_session_authenticates_once_over_verified_tls_and_allowlists_calls(tmp_path):
    factory = Factory()
    session = CredentialSafeTrueNASClient(
        "wss://nas.example/api/current",
        key_file(tmp_path),
        client_factory=factory,
    )
    assert session.call("auth.me")["privilege"]["roles"]
    assert session.call("replication.query", [], {})
    assert len(factory.instances) == 1
    assert factory.kwargs == [
        {
            "uri": "wss://nas.example/api/current",
            "verify_ssl": True,
            "py_exceptions": False,
            "call_timeout": 10.0,
        }
    ]
    methods = [item[0] for item in factory.instances[0].calls]
    assert methods == [
        "auth.login_with_api_key",
        "auth.me",
        "replication.query",
    ]
    assert factory.instances[0].calls[0][1] == (SECRET,)
    assert SECRET not in json.dumps(session.status())
    with pytest.raises(ValueError, match="not passive allowlisted"):
        session.call("system.shutdown")
    session.close()
    assert factory.instances[0].closed is True


def test_session_sanitizes_authentication_and_upstream_errors(tmp_path):
    for factory in (Factory(authenticated=False), Factory(failure=SECRET)):
        session = CredentialSafeTrueNASClient(
            "wss://nas.example/api/current",
            key_file(tmp_path),
            client_factory=factory,
        )
        with pytest.raises(RuntimeError) as captured:
            session.call("auth.me")
        assert str(captured.value) == "credential-safe TrueNAS session unavailable"
        assert SECRET not in str(captured.value)
        assert captured.value.__cause__ is None
        assert factory.instances[0].closed is True


def test_authenticated_observer_reaches_ready_without_publishing_secret(tmp_path):
    factory = Factory()
    result = observe_authenticated(
        "incident-1",
        receipt_store(tmp_path),
        api_uri="wss://nas.example/api/current",
        api_key_file=key_file(tmp_path),
        client_factory=factory,
    )
    assert result["runtime_status"] == "READY"
    assert result["restore_verified"] is True
    assert result["role_verification"]["least_privilege_verified"] is True
    assert result["session"]["tls_certificate_verification"] is True
    assert result["session"]["authenticated"] is True
    assert result["control_authority"] is False
    assert result["deployment_changed"] is False
    assert SECRET not in json.dumps(result)
    assert "not-published" not in json.dumps(result)


def test_authenticated_observer_holds_on_overprivilege_and_missing_client(tmp_path):
    full_admin = Factory(roles=sorted(REQUIRED_ROLES | {"FULL_ADMIN"}))
    held = observe_authenticated(
        "incident-1",
        receipt_store(tmp_path),
        api_uri="wss://nas.example/api/current",
        api_key_file=key_file(tmp_path),
        client_factory=full_admin,
    )
    assert held["runtime_status"] == "HOLD"
    assert held["role_verification"]["forbidden_roles"] == ["FULL_ADMIN"]
    methods = [item[0] for item in full_admin.instances[0].calls]
    assert methods == ["auth.login_with_api_key", "auth.me"]

    missing = observe_authenticated(
        "incident-1",
        receipt_store(tmp_path),
        api_uri="wss://nas.example/api/current",
        api_key_file=tmp_path / "missing.key",
        client_factory=Factory(),
    )
    assert missing["runtime_status"] == "HOLD"
    assert missing["session"]["authenticated"] is False
    assert missing["control_authority"] is False

    downgraded = observe_authenticated(
        "incident-1",
        receipt_store(tmp_path),
        api_uri="ws://nas.example/api/current",
        api_key_file=key_file(tmp_path),
        client_factory=Factory(),
    )
    assert downgraded["runtime_status"] == "HOLD"
    assert downgraded["session"]["transport"] == "rejected"
    assert downgraded["session"]["tls_certificate_verification"] is False
