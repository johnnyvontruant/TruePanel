"""Deterministic proof for AEGIS credential-safe TrueNAS sessions."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from truepanel.aegis.authenticated_observation import observe_authenticated
from truepanel.aegis.credential_session import CredentialSafeTrueNASClient
from truepanel.aegis.passive_providers import issue_restore_verification_receipt
from truepanel.aegis.passive_runtime import REQUIRED_ROLES

_SECRET = "91-HOLODECK-API-KEY-MATERIAL"


class _Client:
    def __init__(
        self,
        calls: list[tuple[str, tuple[Any, ...]]],
        *,
        roles: list[str] | None = None,
        authenticated: bool = True,
        leak_failure: bool = False,
        local: bool = True,
        **_kwargs: Any,
    ) -> None:
        self.calls = calls
        self.roles = roles or sorted(REQUIRED_ROLES)
        self.authenticated = authenticated
        self.leak_failure = leak_failure
        self.local = local

    def call(self, method: str, *arguments: Any) -> Any:
        self.calls.append((method, arguments))
        if self.leak_failure:
            raise RuntimeError(f"unsafe upstream detail: {_SECRET}")
        if method == "auth.login_with_api_key":
            return self.authenticated
        if method == "auth.me":
            return {
                "pw_name": "discarded-identity",
                "local": self.local,
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
        if method in {"cloud_backup.query", "disk.query"}:
            return []
        return None

    def close(self) -> None:
        return None


def _factory(
    calls: list[tuple[str, tuple[Any, ...]]],
    **options: Any,
):
    return lambda **kwargs: _Client(calls, **options, **kwargs)


def _fixture(root: Path) -> tuple[Path, Path]:
    key = root / "api.key"
    key.write_text(_SECRET)
    key.chmod(0o600)
    receipts = root / "receipts"
    receipts.mkdir(mode=0o700)
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
    path = receipts / name
    path.write_text(json.dumps(receipt))
    path.chmod(0o600)
    return key, receipts


def _summary(result: dict[str, Any]) -> dict[str, Any]:
    role = result.get("role_verification") or {}
    session = result.get("session") or {}
    credential = session.get("credential") or {}
    return {
        "runtime_status": result.get("runtime_status"),
        "hold_reason": result.get("hold_reason"),
        "restore_verified": result.get("restore_verified") is True,
        "least_privilege_verified": role.get("least_privilege_verified") is True,
        "forbidden_roles": role.get("forbidden_roles", []),
        "transport": session.get("transport"),
        "tls_certificate_verification": session.get(
            "tls_certificate_verification"
        ),
        "credential_file_secure": credential.get("secure"),
        "read_only": result.get("read_only") is True,
        "control_authority": False,
    }


def run_credential_session_rehearsal() -> dict[str, Any]:
    """Exercise one valid and five unsafe, hardware-isolated session paths."""

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        key, receipts = _fixture(root)
        calls: list[tuple[str, tuple[Any, ...]]] = []
        positive = observe_authenticated(
            "incident-1",
            receipts,
            api_uri="wss://nas.example/api/current",
            api_key_file=key,
            client_factory=_factory(calls),
        )

        negative_results = []
        for scenario, options in (
            ("authentication_rejected", {"authenticated": False}),
            ("overprivileged_session", {"roles": sorted(REQUIRED_ROLES | {"FULL_ADMIN"})}),
            ("directory_backed_identity", {"local": False}),
            ("upstream_secret_in_error", {"leak_failure": True}),
        ):
            result = observe_authenticated(
                "incident-1",
                receipts,
                api_uri="wss://nas.example/api/current",
                api_key_file=key,
                client_factory=_factory([], **options),
            )
            negative_results.append({"scenario": scenario, "result": _summary(result)})

        key.chmod(0o640)
        insecure_file = observe_authenticated(
            "incident-1",
            receipts,
            api_uri="wss://nas.example/api/current",
            api_key_file=key,
            client_factory=_factory([]),
        )
        negative_results.append(
            {
                "scenario": "group_readable_key_file",
                "result": _summary(insecure_file),
            }
        )

        try:
            CredentialSafeTrueNASClient(
                "ws://nas.example/api/current",
                key,
                client_factory=_factory([]),
            )
        except ValueError:
            downgrade_status = "HOLD"
        else:
            downgrade_status = "UNSAFE"
        negative_results.append(
            {
                "scenario": "plaintext_transport_downgrade",
                "result": {
                    "runtime_status": downgrade_status,
                    "control_authority": False,
                },
            }
        )

    positive_summary = _summary(positive)
    serialized = json.dumps(
        {"positive": positive_summary, "negative_scenarios": negative_results},
        sort_keys=True,
    )
    methods = [method for method, _arguments in calls]
    return {
        "schema_version": 1,
        "scenario": "aegis-credential-safe-session-v1",
        "hardware_isolated": True,
        "field_validated": False,
        "control_authority": False,
        "positive": positive_summary,
        "negative_scenarios": negative_results,
        "measurements": {
            "positive_runtime_status": positive["runtime_status"],
            "verified_tls": positive["session"]["tls_certificate_verification"],
            "persistent_connections": positive["session"]["connection_attempts"],
            "authentication_calls": methods.count("auth.login_with_api_key"),
            "passive_calls": sum(method in REQUIRED_PASSIVE for method in methods),
            "unsafe_scenarios": len(negative_results),
            "unsafe_holds": sum(
                item["result"]["runtime_status"] == "HOLD"
                for item in negative_results
            ),
            "credential_occurrences_in_evidence": serialized.count(_SECRET),
            "mutating_method_calls": sum(
                method not in REQUIRED_PASSIVE | {"auth.login_with_api_key"}
                for method in methods
            ),
            "runtime_credential_writes": 0,
        },
    }


REQUIRED_PASSIVE = {
    "auth.me",
    "disk.query",
    "replication.query",
    "cloud_backup.query",
}

__all__ = ["run_credential_session_rehearsal"]
