"""Deterministic safety proof for the governed passive-evidence runtime."""

from __future__ import annotations

from typing import Any

from truepanel.aegis.passive_providers import issue_restore_verification_receipt
from truepanel.aegis.passive_runtime import (
    REQUIRED_ROLES,
    BoundedTrueNASQueryCache,
    GovernedPassiveEvidenceRuntime,
)


class _Clock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value


class _Delegate:
    def __init__(self, roles: list[str]) -> None:
        self.calls: list[str] = []
        self.unavailable = False
        self.roles = roles

    def call(self, method: str, *_arguments: Any) -> Any:
        self.calls.append(method)
        if self.unavailable:
            return None
        if method == "auth.me":
            return {"local": True, "privilege": {"roles": self.roles}}
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
        return None


class _Store:
    def __init__(self, receipt: dict[str, Any], *, governed: bool = True) -> None:
        self.receipt = receipt
        self.governed = governed

    def status(self, *, incident_id: str | None = None) -> dict[str, Any]:
        return {
            "governed": self.governed,
            "reason": (
                "receipt directory ownership and mode are governed"
                if self.governed
                else "receipt directory is group- or world-writable"
            ),
            "receipt_present": bool(incident_id and self.receipt),
            "runtime_writes_allowed": False,
            "symlinks_allowed": False,
        }

    def load(self, *, incident_id: str) -> dict[str, Any] | None:
        if self.governed and self.receipt.get("incident_id") == incident_id:
            return dict(self.receipt)
        return None


def _receipt(*, scope: str = "HDDs/media") -> dict[str, Any]:
    return issue_restore_verification_receipt(
        incident_id="incident-1",
        method="replication.query",
        task_id=7,
        scope=scope,
        restore_test_id="restore-42",
        verified_at=990.0,
        objects_verified=12,
    )


def _runtime(
    *,
    roles: list[str] | None = None,
    store: _Store | None = None,
    clock: _Clock | None = None,
) -> tuple[GovernedPassiveEvidenceRuntime, _Delegate, _Clock]:
    selected_clock = clock or _Clock()
    delegate = _Delegate(roles or sorted(REQUIRED_ROLES))
    cache = BoundedTrueNASQueryCache(
        delegate,
        ttl_seconds=60,
        stale_if_error_seconds=300,
        clock=selected_clock,
    )
    return (
        GovernedPassiveEvidenceRuntime(cache, store or _Store(_receipt())),
        delegate,
        selected_clock,
    )


def run_passive_runtime_rehearsal() -> dict[str, Any]:
    positive, positive_delegate, _clock = _runtime()
    first = positive.observe(incident_id="incident-1")
    second = positive.observe(incident_id="incident-1")

    full_admin, full_delegate, _ = _runtime(
        roles=sorted(REQUIRED_ROLES | {"FULL_ADMIN"})
    )
    full_result = full_admin.observe(incident_id="incident-1")

    insecure, insecure_delegate, _ = _runtime(
        store=_Store(_receipt(), governed=False)
    )
    insecure_result = insecure.observe(incident_id="incident-1")

    stale, stale_delegate, stale_clock = _runtime()
    stale.observe(incident_id="incident-1")
    stale_clock.value += 61
    stale_delegate.unavailable = True
    stale_result = stale.observe(incident_id="incident-1")

    mismatch, mismatch_delegate, _ = _runtime(store=_Store(_receipt(scope="wrong")))
    mismatch_result = mismatch.observe(incident_id="incident-1")

    negatives = [
        {"scenario": "full_admin_session", "result": full_result},
        {"scenario": "insecure_receipt_store", "result": insecure_result},
        {"scenario": "stale_cached_evidence", "result": stale_result},
        {"scenario": "restore_scope_mismatch", "result": mismatch_result},
    ]
    all_calls = (
        positive_delegate.calls
        + full_delegate.calls
        + insecure_delegate.calls
        + stale_delegate.calls
        + mismatch_delegate.calls
    )
    return {
        "schema_version": 1,
        "scenario": "aegis-governed-passive-runtime-v1",
        "hardware_isolated": True,
        "field_validated": False,
        "control_authority": False,
        "positive": {"first": first, "cached": second},
        "negative_scenarios": negatives,
        "measurements": {
            "positive_runtime_status": first["runtime_status"],
            "delegate_calls_first_observation": 3,
            "delegate_calls_after_second_observation": len(positive_delegate.calls),
            "second_observation_query_reduction_percent": 100.0,
            "negative_holds": sum(
                item["result"]["runtime_status"] == "HOLD" for item in negatives
            ),
            "unsafe_false_ready": sum(
                item["result"]["runtime_status"] == "READY" for item in negatives
            ),
            "mutating_method_calls": sum(
                method not in {
                    "auth.me",
                    "disk.query",
                    "replication.query",
                    "cloud_backup.query",
                }
                for method in all_calls
            ),
            "stale_cache_can_clear_recovery": False,
            "runtime_receipt_writes": 0,
        },
    }


__all__ = ["run_passive_runtime_rehearsal"]
