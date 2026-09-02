import hashlib
import json
from types import SimpleNamespace

import pytest

from truepanel.aegis.passive_observation import observe
from truepanel.aegis.passive_providers import (
    TrueNASReadOnlyQueryClient,
    issue_restore_verification_receipt,
)
from truepanel.aegis.passive_runtime import (
    REQUIRED_ROLES,
    BoundedTrueNASQueryCache,
    GovernedPassiveEvidenceRuntime,
    GovernedRestoreReceiptStore,
    TrueNASRoleVerifier,
)


class Clock:
    def __init__(self, value=100.0):
        self.value = value

    def __call__(self):
        return self.value


class Delegate:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []
        self.unavailable = set()

    def call(self, method, *arguments):
        self.calls.append((method, arguments))
        if method in self.unavailable:
            return None
        return self.responses.get(method)


def identity(*roles):
    return {
        "local": True,
        "pw_name": "not-published",
        "privilege": {"roles": list(roles)},
    }


def secure_store(tmp_path, *, incident_id="incident-1", receipt=None):
    root = tmp_path / "receipts"
    root.mkdir(mode=0o700)
    if receipt is not None:
        name = hashlib.sha256(incident_id.encode()).hexdigest() + ".json"
        path = root / name
        path.write_text(json.dumps(receipt))
        path.chmod(0o600)
    return GovernedRestoreReceiptStore(root)


def test_query_client_auth_me_is_parameterless_and_write_calls_are_blocked():
    calls = []

    def runner(command, **_kwargs):
        calls.append(command)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(identity(*REQUIRED_ROLES)),
        )

    client = TrueNASReadOnlyQueryClient(runner=runner, executable="/usr/bin/midclt")
    result = client.call("auth.me")
    assert result["privilege"]["roles"]
    assert calls == [["/usr/bin/midclt", "call", "auth.me"]]
    with pytest.raises(ValueError, match="not passive allowlisted"):
        client.call("system.shutdown")


def test_cache_bounds_calls_reuses_stale_data_and_limits_entries():
    clock = Clock()
    delegate = Delegate({"disk.query": [{"name": "sda"}]})
    cache = BoundedTrueNASQueryCache(
        delegate,
        ttl_seconds=10,
        stale_if_error_seconds=20,
        max_entries=2,
        clock=clock,
    )

    assert cache.query("disk.query") == [{"name": "sda"}]
    assert cache.query("disk.query") == [{"name": "sda"}]
    assert len(delegate.calls) == 1
    clock.value += 11
    delegate.unavailable.add("disk.query")
    assert cache.query("disk.query") == [{"name": "sda"}]
    assert cache.metrics()["stale_hits"] == 1
    clock.value += 21
    assert cache.query("disk.query") == []
    assert cache.metrics()["entries"] <= 2


def test_cache_configuration_is_strictly_bounded():
    delegate = Delegate({})
    with pytest.raises(ValueError, match="TTL"):
        BoundedTrueNASQueryCache(delegate, ttl_seconds=5)
    with pytest.raises(ValueError, match="stale-if-error"):
        BoundedTrueNASQueryCache(delegate, stale_if_error_seconds=3601)
    with pytest.raises(ValueError, match="between 1 and 8"):
        BoundedTrueNASQueryCache(delegate, max_entries=9)


def test_role_verifier_requires_read_roles_and_rejects_any_write_authority():
    good = Delegate({"auth.me": identity(*REQUIRED_ROLES)})
    verified = TrueNASRoleVerifier(good).verify()
    assert verified["status"] == "VERIFIED"
    assert verified["least_privilege_verified"] is True
    assert "not-published" not in json.dumps(verified)

    full = Delegate({"auth.me": identity(*REQUIRED_ROLES, "FULL_ADMIN")})
    assert TrueNASRoleVerifier(full).verify()["status"] == "HOLD"
    write = Delegate({"auth.me": identity(*REQUIRED_ROLES, "DISK_WRITE")})
    assert TrueNASRoleVerifier(write).verify()["status"] == "HOLD"
    missing = Delegate({"auth.me": identity("READONLY_ADMIN")})
    result = TrueNASRoleVerifier(missing).verify()
    assert result["status"] == "HOLD"
    assert result["missing_roles"]


def test_receipt_store_requires_secure_owner_mode_and_incident_binding(tmp_path):
    receipt = {"incident_id": "incident-1", "value": "fixture"}
    store = secure_store(tmp_path, receipt=receipt)
    assert store.status(incident_id="incident-1")["governed"] is True
    assert store.load(incident_id="incident-1") == receipt
    assert store.load(incident_id="other") is None

    root = tmp_path / "open"
    root.mkdir(mode=0o777)
    root.chmod(0o777)
    result = GovernedRestoreReceiptStore(root).status()
    assert result["governed"] is False
    assert "writable" in result["reason"]


def test_receipt_store_rejects_symlink_and_mutable_or_oversized_files(tmp_path):
    root = tmp_path / "receipts"
    root.mkdir(mode=0o700)
    incident = "incident-1"
    name = hashlib.sha256(incident.encode()).hexdigest() + ".json"
    target = tmp_path / "target.json"
    target.write_text(json.dumps({"incident_id": incident}))
    (root / name).symlink_to(target)
    store = GovernedRestoreReceiptStore(root)
    assert store.load(incident_id=incident) is None

    (root / name).unlink()
    (root / name).write_text(json.dumps({"incident_id": incident}))
    (root / name).chmod(0o666)
    assert store.load(incident_id=incident) is None
    (root / name).write_bytes(b"x" * (64 * 1024 + 1))
    (root / name).chmod(0o600)
    assert store.load(incident_id=incident) is None


def test_runtime_stops_after_role_hold_without_querying_protection_data(tmp_path):
    delegate = Delegate(
        {
            "auth.me": identity(*REQUIRED_ROLES, "FULL_ADMIN"),
            "replication.query": [],
            "cloud_backup.query": [],
        }
    )
    cache = BoundedTrueNASQueryCache(delegate)
    runtime = GovernedPassiveEvidenceRuntime(cache, secure_store(tmp_path))
    result = runtime.observe(incident_id="incident-1")
    assert result["runtime_status"] == "HOLD"
    assert result["role_verification"]["forbidden_roles"] == ["FULL_ADMIN"]
    assert [item[0] for item in delegate.calls] == ["auth.me"]
    assert result["control_authority"] is False


def test_runtime_uses_governed_receipt_and_cache_without_repolling(tmp_path):
    receipt = issue_restore_verification_receipt(
        incident_id="incident-1",
        method="replication.query",
        task_id=7,
        scope="HDDs/media",
        restore_test_id="restore-42",
        verified_at=990.0,
        objects_verified=12,
    )
    delegate = Delegate(
        {
            "auth.me": identity(*REQUIRED_ROLES),
            "replication.query": [
                {
                    "id": 7,
                    "enabled": True,
                    "source_datasets": ["HDDs/media"],
                    "state": {"state": "SUCCESS"},
                }
            ],
            "cloud_backup.query": [],
        }
    )
    cache = BoundedTrueNASQueryCache(delegate)
    runtime = GovernedPassiveEvidenceRuntime(
        cache,
        secure_store(tmp_path, receipt=receipt),
    )
    first = runtime.observe(incident_id="incident-1")
    second = runtime.observe(incident_id="incident-1")
    assert first["runtime_status"] == "READY"
    assert first["restore_verified"] is True
    assert first["control_authority"] is False
    assert second["cache"]["delegate_calls"] == 3
    assert second["cache"]["cache_hits"] == 3
    assert len(delegate.calls) == 3


def test_runtime_demotes_stale_cache_to_display_only_hold(tmp_path):
    clock = Clock()
    receipt = issue_restore_verification_receipt(
        incident_id="incident-1",
        method="replication.query",
        task_id=7,
        scope="HDDs/media",
        restore_test_id="restore-42",
        verified_at=990.0,
        objects_verified=12,
    )
    delegate = Delegate(
        {
            "auth.me": identity(*REQUIRED_ROLES),
            "replication.query": [
                {
                    "id": 7,
                    "enabled": True,
                    "source_datasets": ["HDDs/media"],
                    "state": {"state": "SUCCESS"},
                }
            ],
            "cloud_backup.query": [],
        }
    )
    cache = BoundedTrueNASQueryCache(delegate, ttl_seconds=10, clock=clock)
    runtime = GovernedPassiveEvidenceRuntime(
        cache,
        secure_store(tmp_path, receipt=receipt),
    )
    assert runtime.observe(incident_id="incident-1")["runtime_status"] == "READY"
    clock.value += 11
    delegate.unavailable.update(
        {"auth.me", "replication.query", "cloud_backup.query"}
    )
    stale = runtime.observe(incident_id="incident-1")
    assert stale["runtime_status"] == "HOLD"
    assert stale["restore_verified"] is False
    assert "display-only" in stale["hold_reason"]
    assert "backup_context" not in stale


def test_no_deploy_observation_is_stdout_safe_and_cannot_claim_authority(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("shutil.which", lambda _name: None)
    result = observe("incident-1", tmp_path / "missing")
    assert result["operation"] == "passive_no_deploy_observation"
    assert result["runtime_status"] == "HOLD"
    assert result["deployment_changed"] is False
    assert result["control_authority"] is False
    assert "tasks" not in result
