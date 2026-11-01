"""Attach deterministic Lifeline repair sessions to operator guidance."""

from __future__ import annotations

from typing import Any

from .session import evaluate_drive_repair


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _candidate_for(
    target: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any] | None:
    candidates = context.get("replacement_candidates")
    if not isinstance(candidates, list):
        return None

    target_bay = target.get("bay")
    target_device = str(target.get("device") or "").strip()

    def prepare(value: dict[str, Any]) -> dict[str, Any]:
        item = dict(value)
        candidate_device = str(item.get("device") or "").strip()

        # A hot-swap may legitimately reuse the old /dev/sdX path. Permit
        # that only when replacement discovery has independently proven that
        # the attached hardware identity differs from the original disk.
        if (
            target_device
            and candidate_device == target_device
            and item.get("identity_verified_distinct") is not True
        ):
            item["ambiguous"] = True

        if target_bay is not None and item.get("bay") is None:
            item["expected_bay"] = target_bay
        return item

    # Prefer an explicitly selected candidate. If none is selected, only use
    # the candidate automatically when exactly one record exists.
    selected = [
        item
        for item in candidates
        if isinstance(item, dict) and item.get("selected") is True
    ]
    if len(selected) == 1:
        return prepare(selected[0])
    if selected:
        return {"ambiguous": True}

    usable = [
        item
        for item in candidates
        if isinstance(item, dict)
    ]
    if len(usable) == 1:
        return prepare(usable[0])
    if len(usable) > 1:
        return {"ambiguous": True}
    return None


def attach_repair_sessions(
    guidance: list[dict[str, Any]],
    *,
    context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return guidance with additive, read-only Lifeline session payloads."""

    context = _dict(context)
    results: list[dict[str, Any]] = []

    for item in guidance if isinstance(guidance, list) else []:
        if not isinstance(item, dict):
            continue

        payload = dict(item)
        if payload.get("code") != "storage.disk_faulted":
            results.append(payload)
            continue

        runtime = _dict(payload.get("runtime"))
        evidence = _dict(runtime.get("evidence"))
        target = {
            "bay": evidence.get("bay"),
            "device": evidence.get("device"),
        }
        acknowledgements = _dict(context.get("acknowledgements"))
        repair = evaluate_drive_repair(
            evidence,
            service_procedure_verified=bool(
                context.get("service_procedure_verified", False)
            ),
            backup_acknowledged=bool(
                acknowledgements.get("backup_state", False)
            ),
            bay_identity_verified=context.get("bay_identity_verified"),
            replacement_candidate=_candidate_for(target, context),
            replacement_operation_confirmed=bool(
                acknowledgements.get("replacement_operation", False)
            ),
        )
        payload["repair_session"] = repair.to_payload()
        results.append(payload)

    return results


__all__ = ["attach_repair_sessions"]
