"""Critical-SMART pre-failure handoff for Project Lifeline.

This extension preserves the established ZFS-fault repair contract while
allowing replacement-worthy SMART evidence to open a metadata-only Lifeline
session before ZFS marks the member unhealthy. Linux ``sdX`` names are treated
as runtime addresses only; persistent incidents use privacy-safe stable drive
identity whenever sufficient evidence exists. It adds no storage mutation
authority.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .identity import DriveIdentity, DriveIdentityResolver
from .store import LifelineSessionStore as _BaseLifelineSessionStore


_DISK_FAULT_CODE = "storage.disk_faulted"
_SMART_WARNING_CODE = "storage.smart_warning"
_REQUIRED_HEALTHY_OBSERVATIONS = 3
_IDENTITY_STRENGTH = {
    "legacy_runtime_address": 0,
    "correlated_evidence": 1,
    "zfs_member": 2,
    "serial_model": 3,
    "wwn": 4,
}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _legacy_fault_key(evidence: dict[str, Any]) -> str | None:
    pool = _text(evidence.get("pool"))
    vdev = _text(evidence.get("vdev"))
    device = _text(evidence.get("device"))
    member_id = _text(evidence.get("member_id") or evidence.get("zfs_name"))
    identity = device or member_id
    if not pool or not vdev or not identity:
        return None
    return f"drive:{pool}:{vdev}:{identity}"


def _stable_fault_key(
    evidence: dict[str, Any],
    identity: DriveIdentity | None,
) -> str | None:
    pool = _text(evidence.get("pool"))
    vdev = _text(evidence.get("vdev"))
    if not pool or not vdev:
        return None
    if identity is None or identity.mode == "legacy_runtime_address":
        return _legacy_fault_key(evidence)
    return f"drive:{pool}:{vdev}:{identity.stable_key}"


def _models_compatible(left: Any, right: Any) -> bool:
    left_text = _text(left).upper()
    right_text = _text(right).upper()
    if not left_text or not right_text:
        return True
    return (
        left_text == right_text
        or left_text.startswith(right_text)
        or right_text.startswith(left_text)
    )


def _identity_strength(value: Any) -> int:
    return _IDENTITY_STRENGTH.get(_text(_dict(value).get("mode")), -1)


def _device_from(value: dict[str, Any]) -> str:
    return _text(value.get("device") or value.get("drive"))


def _pool_state(payload: dict[str, Any], pool_name: str) -> str:
    storage = _dict(payload.get("storage"))
    for pool in _list(storage.get("pools")):
        if not isinstance(pool, dict):
            continue
        if _text(pool.get("name")) != pool_name:
            continue
        return _text(pool.get("health") or pool.get("state")).upper()
    return ""


def _resilver_running(payload: dict[str, Any]) -> bool:
    storage = _dict(payload.get("storage"))
    activity = _dict(storage.get("zfs_activity"))
    return bool(activity.get("resilver_running", False))


def _critical_smart_evidence(evidence: dict[str, Any]) -> bool:
    health = _text(evidence.get("smart_health") or evidence.get("health")).upper()
    warning = _text(evidence.get("critical_warning")).lower()
    return bool(
        health == "FAILED"
        or _integer(evidence.get("pending")) > 0
        or _integer(evidence.get("offline_uncorrectable")) > 0
        or _integer(evidence.get("media_errors")) > 0
        or warning not in {"", "0", "0x0", "0x00"}
    )


def _is_critical_smart_card(
    item: dict[str, Any],
    evidence: dict[str, Any],
) -> bool:
    runtime = _dict(item.get("runtime"))
    return bool(
        item.get("code") == _SMART_WARNING_CODE
        and _text(item.get("severity")).lower() == "critical"
        and _text(runtime.get("disposition")) == "prepare_replacement"
        and _critical_smart_evidence(evidence)
    )


def _device_evidence(
    payload: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """Fill SMART guidance gaps only from one exact storage-device match."""

    merged = dict(evidence)
    storage = _dict(payload.get("storage"))
    target_device = _text(evidence.get("device"))
    target_pool = _text(evidence.get("pool"))
    target_vdev = _text(evidence.get("vdev"))

    matches: list[dict[str, Any]] = []
    for record in _list(storage.get("devices")):
        if not isinstance(record, dict):
            continue
        record_device = _text(record.get("device") or record.get("drive"))
        if not target_device or record_device != target_device:
            continue
        record_pool = _text(record.get("pool"))
        record_vdev = _text(record.get("vdev"))
        if target_pool and record_pool and record_pool != target_pool:
            continue
        if target_vdev and record_vdev and record_vdev != target_vdev:
            continue
        matches.append(record)

    if len(matches) != 1:
        return merged

    record = matches[0]
    aliases = {
        "member_id": ("member_id", "zfs_name"),
        "historical_path": ("historical_path",),
        "vdev_topology": ("vdev_topology",),
        "remaining_redundancy": ("remaining_redundancy",),
        "bay": ("bay", "physical_bay"),
        "model": ("model",),
        "serial_last4": ("serial_last4",),
        "capacity_bytes": ("capacity_bytes",),
        "zfs_state": ("zfs_state", "state"),
    }
    for destination, sources in aliases.items():
        if merged.get(destination) not in (None, ""):
            continue
        for source in sources:
            value = record.get(source)
            if value not in (None, ""):
                merged[destination] = value
                break

    pool_name = _text(merged.get("pool"))
    if pool_name and not _text(merged.get("pool_state")):
        merged["pool_state"] = _pool_state(payload, pool_name)
    return merged


def _same_target(
    evidence: dict[str, Any],
    original: dict[str, Any],
) -> bool:
    pool = _text(original.get("pool"))
    vdev = _text(original.get("vdev"))
    if pool and _text(evidence.get("pool")) != pool:
        return False
    if vdev and _text(evidence.get("vdev")) != vdev:
        return False

    original_bay = original.get("bay")
    evidence_bay = evidence.get("bay") or evidence.get("physical_bay")
    if original_bay is not None and evidence_bay is not None:
        try:
            return int(original_bay) == int(evidence_bay)
        except (TypeError, ValueError):
            return False

    original_device = _text(original.get("device"))
    return bool(
        original_device
        and _text(evidence.get("device") or evidence.get("drive"))
        == original_device
    )


def _strict_metadata_match(
    evidence: dict[str, Any],
    original: dict[str, Any],
) -> bool:
    """Correlate legacy aliases only with independent physical evidence."""

    if not _text(evidence.get("pool")) or not _text(evidence.get("vdev")):
        return False
    if _text(evidence.get("pool")) != _text(original.get("pool")):
        return False
    if _text(evidence.get("vdev")) != _text(original.get("vdev")):
        return False

    try:
        evidence_bay = int(evidence.get("bay") or evidence.get("physical_bay"))
        original_bay = int(original.get("bay") or original.get("physical_bay"))
    except (TypeError, ValueError):
        return False
    if evidence_bay <= 0 or evidence_bay != original_bay:
        return False

    evidence_serial = _text(evidence.get("serial_last4"))
    original_serial = _text(original.get("serial_last4"))
    if not evidence_serial or evidence_serial != original_serial:
        return False

    evidence_model = _text(evidence.get("model"))
    original_model = _text(original.get("model"))
    if not evidence_model or not original_model:
        return False
    if not _models_compatible(evidence_model, original_model):
        return False

    evidence_capacity = _integer(evidence.get("capacity_bytes"))
    original_capacity = _integer(original.get("capacity_bytes"))
    if evidence_capacity and original_capacity and evidence_capacity != original_capacity:
        return False
    return True


def _smart_warning_present(
    guidance: list[Any],
    original: dict[str, Any],
) -> bool:
    for item in guidance:
        if not isinstance(item, dict) or item.get("code") != _SMART_WARNING_CODE:
            continue
        evidence = _dict(_dict(item.get("runtime")).get("evidence"))
        if _same_target(evidence, original):
            return True
    return False


def _replacement_identity_observed(
    payload: dict[str, Any],
    original: dict[str, Any],
) -> bool:
    """Require a new serial suffix in the exact original bay, fail closed."""

    pool = _text(original.get("pool"))
    original_serial = _text(original.get("serial_last4"))
    original_bay = original.get("bay")
    if not pool or not original_serial or original_bay is None:
        return False

    storage = _dict(payload.get("storage"))
    matches: list[dict[str, Any]] = []
    for record in _list(storage.get("smart")):
        if not isinstance(record, dict):
            continue
        if _text(record.get("pool")) != pool:
            continue
        bay = record.get("bay") or record.get("physical_bay")
        try:
            same_bay = int(bay) == int(original_bay)
        except (TypeError, ValueError):
            same_bay = False
        if same_bay:
            matches.append(record)

    if len(matches) != 1:
        return False

    record = matches[0]
    state = _text(record.get("zfs_state") or record.get("state")).upper()
    replacement_serial = _text(record.get("serial_last4"))
    warning = _text(record.get("critical_warning")).lower()
    smart_clean = bool(
        _text(record.get("health")).upper() != "FAILED"
        and _integer(record.get("reallocated")) == 0
        and _integer(record.get("pending")) == 0
        and _integer(record.get("offline_uncorrectable")) == 0
        and _integer(record.get("reported_uncorrect")) == 0
        and _integer(record.get("media_errors")) == 0
        and warning in {"", "0", "0x0", "0x00"}
    )
    return bool(
        state == "ONLINE"
        and smart_clean
        and replacement_serial
        and replacement_serial != original_serial
    )


class LifelineSessionStore(_BaseLifelineSessionStore):
    """Add critical-SMART recovery plus stable physical-drive identity."""

    def __init__(self, path=None, *, clock=None, identity_resolver=None) -> None:
        super().__init__(path=path, clock=clock)
        self.identity_resolver = identity_resolver or DriveIdentityResolver()

    @staticmethod
    def _public_identity(identity: DriveIdentity | None) -> dict[str, Any] | None:
        return identity.to_public_dict() if identity is not None else None

    def _new_smart_session(
        self,
        key: str,
        evidence: dict[str, Any],
        *,
        identity: DriveIdentity | None = None,
    ) -> dict[str, Any]:
        ledger = super()._new_session(key, evidence)
        ledger["trigger_code"] = _SMART_WARNING_CODE
        ledger["trigger_kind"] = "critical_smart_prefailure"
        ledger["original_fault"]["zfs_state"] = evidence.get("zfs_state")
        ledger["trigger"] = {
            "severity": "critical",
            "disposition": "prepare_replacement",
        }
        self._record_identity(ledger, identity, evidence)
        return ledger

    @staticmethod
    def _trigger_code(ledger: dict[str, Any]) -> str:
        return _text(ledger.get("trigger_code")) or _DISK_FAULT_CODE

    @staticmethod
    def _session_evidence(ledger: dict[str, Any]) -> dict[str, Any]:
        evidence = dict(_dict(ledger.get("original_fault")))
        target = _dict(_dict(ledger.get("last_session")).get("target"))
        for key, value in target.items():
            if evidence.get(key) in (None, "") and value not in (None, ""):
                evidence[key] = value
        return evidence

    @staticmethod
    def _record_device_history(
        ledger: dict[str, Any],
        *devices: Any,
    ) -> bool:
        existing = [
            _text(item)
            for item in _list(ledger.get("device_history"))
            if _text(item)
        ]
        changed = False
        for value in devices:
            device = _text(value)
            if not device or device in existing:
                continue
            existing.append(device)
            changed = True
        if ledger.get("device_history") != existing:
            ledger["device_history"] = existing
            changed = True
        return changed

    def _record_identity(
        self,
        ledger: dict[str, Any],
        identity: DriveIdentity | None,
        evidence: dict[str, Any],
    ) -> bool:
        changed = False
        device = _device_from(evidence)
        if self._record_device_history(
            ledger,
            _device_from(_dict(ledger.get("original_fault"))),
            device,
        ):
            changed = True
        if device and ledger.get("current_device") != device:
            ledger["current_device"] = device
            changed = True

        current_identity = _dict(ledger.get("drive_identity"))
        current_strength = _identity_strength(current_identity)
        incoming = self._public_identity(identity)
        incoming_strength = _identity_strength(incoming)
        same_identity = bool(
            incoming
            and _text(current_identity.get("stable_key"))
            == _text(incoming.get("stable_key"))
        )
        if incoming and (
            not current_identity
            or same_identity
            or incoming_strength > current_strength
        ):
            if current_identity != incoming:
                ledger["drive_identity"] = incoming
                changed = True
        return changed

    @staticmethod
    def _identity_conflicts(
        ledger: dict[str, Any],
        identity: DriveIdentity | None,
    ) -> bool:
        if identity is None:
            return False
        existing = _dict(ledger.get("drive_identity"))
        if not existing:
            return False
        existing_key = _text(existing.get("stable_key"))
        if not existing_key or existing_key == identity.stable_key:
            return False
        existing_strength = _identity_strength(existing)
        incoming_strength = _IDENTITY_STRENGTH.get(identity.mode, -1)
        return bool(
            existing_strength == incoming_strength
            and existing_strength >= _IDENTITY_STRENGTH["zfs_member"]
        )

    def _matching_active_sessions(
        self,
        evidence: dict[str, Any],
        identity: DriveIdentity | None,
    ) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        for ledger in self._state["sessions"].values():
            if not isinstance(ledger, dict) or ledger.get("status") != "active":
                continue
            existing_identity = _dict(ledger.get("drive_identity"))
            if (
                identity is not None
                and _text(existing_identity.get("stable_key"))
                == identity.stable_key
            ):
                matches.append(ledger)
                continue
            if self._identity_conflicts(ledger, identity):
                continue
            if _strict_metadata_match(evidence, self._session_evidence(ledger)):
                matches.append(ledger)
        return matches

    @staticmethod
    def _canonical_session(
        candidates: list[dict[str, Any]],
        evidence: dict[str, Any],
        preferred_key: str,
    ) -> dict[str, Any] | None:
        if not candidates:
            return None
        for ledger in candidates:
            if _text(ledger.get("fault_key")) == preferred_key:
                return ledger
        device = _device_from(evidence)
        if device:
            current = [
                ledger
                for ledger in candidates
                if _device_from(_dict(ledger.get("original_fault"))) == device
                or _text(ledger.get("current_device")) == device
            ]
            if current:
                return max(
                    current,
                    key=lambda item: float(item.get("updated_at", 0.0) or 0.0),
                )
        return max(
            candidates,
            key=lambda item: float(item.get("updated_at", 0.0) or 0.0),
        )

    def _effective_fault_key(
        self,
        ledger: dict[str, Any],
        proposed_key: str,
        identity: DriveIdentity | None,
    ) -> str:
        existing_identity = _dict(ledger.get("drive_identity"))
        existing_strength = _identity_strength(existing_identity)
        incoming_strength = (
            _IDENTITY_STRENGTH.get(identity.mode, -1)
            if identity is not None
            else -1
        )
        existing_key = _text(ledger.get("fault_key"))
        if existing_identity and existing_strength > incoming_strength and existing_key:
            return existing_key
        return proposed_key

    def _rekey_session(
        self,
        ledger: dict[str, Any],
        key: str,
    ) -> bool:
        sessions = self._state["sessions"]
        old_id = _text(ledger.get("id"))
        old_key = _text(ledger.get("fault_key"))
        if old_key == key and old_id in sessions:
            return False

        attempt = int(ledger.get("attempt", 1) or 1)
        new_id = f"{key}:attempt-{attempt}"
        collision = sessions.get(new_id)
        if collision is not None and collision is not ledger:
            attempt = self._next_attempt(key)
            ledger["attempt"] = attempt
            new_id = f"{key}:attempt-{attempt}"

        legacy_ids = [
            _text(value)
            for value in _list(ledger.get("legacy_ids"))
            if _text(value)
        ]
        legacy_keys = [
            _text(value)
            for value in _list(ledger.get("legacy_fault_keys"))
            if _text(value)
        ]
        if old_id and old_id != new_id and old_id not in legacy_ids:
            legacy_ids.append(old_id)
        if old_key and old_key != key and old_key not in legacy_keys:
            legacy_keys.append(old_key)

        if old_id and sessions.get(old_id) is ledger:
            sessions.pop(old_id)
        ledger["id"] = new_id
        ledger["fault_key"] = key
        ledger["legacy_ids"] = legacy_ids
        ledger["legacy_fault_keys"] = legacy_keys
        sessions[new_id] = ledger
        return True

    def _merge_alias_sessions(
        self,
        canonical: dict[str, Any],
        candidates: list[dict[str, Any]],
        *,
        key: str,
        identity: DriveIdentity | None,
        evidence: dict[str, Any],
        now: float,
    ) -> bool:
        changed = False
        ordered = sorted(
            candidates,
            key=lambda item: (
                float(item.get("created_at", 0.0) or 0.0),
                _text(item.get("id")),
            ),
        )
        for ledger in ordered:
            original = self._session_evidence(ledger)
            if self._record_device_history(
                canonical,
                *_list(ledger.get("device_history")),
                _device_from(original),
            ):
                changed = True

        effective_key = self._effective_fault_key(canonical, key, identity)
        if self._rekey_session(canonical, effective_key):
            changed = True
        if self._record_identity(canonical, identity, evidence):
            changed = True

        original = _dict(canonical.get("original_fault"))
        current_device = _device_from(evidence)
        if current_device and original.get("device") != current_device:
            original["device"] = current_device
            changed = True
        member_id = evidence.get("member_id") or evidence.get("zfs_name")
        if member_id not in (None, "") and original.get("member_id") != member_id:
            original["member_id"] = member_id
            changed = True
        canonical["original_fault"] = original

        canonical_id = _text(canonical.get("id"))
        legacy_ids = [
            _text(value)
            for value in _list(canonical.get("legacy_ids"))
            if _text(value)
        ]
        legacy_keys = [
            _text(value)
            for value in _list(canonical.get("legacy_fault_keys"))
            if _text(value)
        ]
        for ledger in ordered:
            if ledger is canonical:
                continue
            alias_id = _text(ledger.get("id"))
            alias_key = _text(ledger.get("fault_key"))
            if alias_id and alias_id not in legacy_ids:
                legacy_ids.append(alias_id)
            if alias_key and alias_key not in legacy_keys:
                legacy_keys.append(alias_key)
            if ledger.get("status") != "superseded":
                ledger["status"] = "superseded"
                changed = True
            if ledger.get("superseded_by") != canonical_id:
                ledger["superseded_by"] = canonical_id
                changed = True
            ledger["superseded_at"] = now
            ledger["updated_at"] = now
        if canonical.get("legacy_ids") != legacy_ids:
            canonical["legacy_ids"] = legacy_ids
            changed = True
        if canonical.get("legacy_fault_keys") != legacy_keys:
            canonical["legacy_fault_keys"] = legacy_keys
            changed = True
        return changed

    def _resolve_active_session(
        self,
        evidence: dict[str, Any],
        identity: DriveIdentity | None,
        *,
        now: float,
    ) -> tuple[dict[str, Any] | None, str | None, bool]:
        proposed_key = _stable_fault_key(evidence, identity)
        if proposed_key is None:
            return None, None, False

        candidates = self._matching_active_sessions(evidence, identity)
        exact = self._active_for_fault(proposed_key)
        if exact is not None and all(item is not exact for item in candidates):
            candidates.append(exact)
        canonical = self._canonical_session(candidates, evidence, proposed_key)
        if canonical is None:
            return None, proposed_key, False

        changed = self._merge_alias_sessions(
            canonical,
            candidates,
            key=proposed_key,
            identity=identity,
            evidence=evidence,
            now=now,
        )
        return canonical, _text(canonical.get("fault_key")), changed

    def _evaluate(
        self,
        ledger: dict[str, Any],
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        if self._trigger_code(ledger) != _SMART_WARNING_CODE:
            return super()._evaluate(ledger, evidence)

        actual_state = _text(evidence.get("zfs_state")).upper() or "ONLINE"
        evaluation_evidence = dict(evidence)
        if actual_state == "ONLINE":
            # The base evaluator correctly requires an unhealthy ZFS state.
            # For this isolated pre-failure route, independently verified
            # critical SMART evidence is the equivalent member-health gate.
            evaluation_evidence["zfs_state"] = "FAULTED"

        repair = super()._evaluate(ledger, evaluation_evidence)
        repair["code"] = _SMART_WARNING_CODE
        repair["title"] = "Guided pre-failure drive recovery"
        repair["summary"] = (
            _text(repair.get("summary"))
            .replace("failed bay", "at-risk bay")
            .replace("failed member", "at-risk member")
        )

        target = _dict(repair.get("target"))
        target["zfs_state"] = actual_state
        target["trigger"] = "critical_smart_prefailure"
        repair["target"] = target

        for gate in _list(repair.get("gates")):
            if not isinstance(gate, dict) or gate.get("code") != "member_identity":
                continue
            gate["title"] = "At-risk member identified"
            gate["detail"] = (
                "Pool, VDEV, exact member identity, and replacement-worthy "
                "critical SMART evidence must agree."
            )
        return repair

    def _prefailure_completion_ready(
        self,
        payload: dict[str, Any],
        guidance: list[Any],
        ledger: dict[str, Any],
    ) -> bool:
        original = _dict(ledger.get("original_fault"))
        context = _dict(ledger.get("context"))
        acknowledgements = _dict(context.get("acknowledgements"))
        last_session = _dict(ledger.get("last_session"))
        replacement = _dict(last_session.get("replacement"))

        return bool(
            context.get("service_procedure_verified") is True
            and acknowledgements.get("backup_state") is True
            and replacement.get("valid") is True
            and not _smart_warning_present(guidance, original)
            and _replacement_identity_observed(payload, original)
        )

    def observe(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = deepcopy(payload)
        guidance = _list(result.get("operator_guidance"))
        now = float(self.clock())
        changed = False
        seen_faults: set[str] = set()

        with self._lock:
            sessions = self._state["sessions"]

            for item in guidance:
                if not isinstance(item, dict):
                    continue
                code = _text(item.get("code"))
                runtime = _dict(item.get("runtime"))
                evidence = _dict(runtime.get("evidence"))

                is_disk_fault = code == _DISK_FAULT_CODE
                is_smart_fault = _is_critical_smart_card(item, evidence)
                if not is_disk_fault and not is_smart_fault:
                    continue

                if is_smart_fault:
                    evidence = _device_evidence(result, evidence)

                identity = self.identity_resolver.resolve(evidence)
                ledger, key, migrated = self._resolve_active_session(
                    evidence,
                    identity,
                    now=now,
                )
                changed = changed or migrated
                if key is None:
                    continue

                if ledger is None:
                    if is_smart_fault:
                        ledger = self._new_smart_session(
                            key,
                            evidence,
                            identity=identity,
                        )
                    else:
                        ledger = super()._new_session(key, evidence)
                        self._record_identity(ledger, identity, evidence)
                    changed = True
                elif (
                    is_disk_fault
                    and self._trigger_code(ledger) == _SMART_WARNING_CODE
                ):
                    # ZFS has now confirmed the fault. Escalate to the original,
                    # stricter ZFS-fault contract and never downgrade later.
                    ledger["trigger_code"] = _DISK_FAULT_CODE
                    ledger["trigger_kind"] = "zfs_fault"
                    changed = True
                elif is_smart_fault and self._trigger_code(ledger) == _DISK_FAULT_CODE:
                    # An established ZFS fault remains authoritative.
                    continue

                if self._record_identity(ledger, identity, evidence):
                    changed = True
                seen_faults.add(_text(ledger.get("fault_key")))
                if ledger.get("healthy_observations") != 0:
                    ledger["healthy_observations"] = 0
                    changed = True
                ledger["updated_at"] = now
                repair = self._evaluate(ledger, evidence)
                if ledger.get("last_session") != repair:
                    ledger["last_session"] = repair
                    changed = True
                item["repair_session"] = deepcopy(repair)

            for ledger in list(sessions.values()):
                if not isinstance(ledger, dict) or ledger.get("status") != "active":
                    continue
                if ledger.get("fault_key") in seen_faults:
                    continue

                original = _dict(ledger.get("original_fault"))
                pool_name = _text(original.get("pool"))
                pool_state = _pool_state(result, pool_name)
                resilver = _resilver_running(result)
                trigger_code = self._trigger_code(ledger)

                healthy_base = pool_state == "ONLINE" and not resilver
                if trigger_code == _SMART_WARNING_CODE:
                    healthy_ready = bool(
                        healthy_base
                        and self._prefailure_completion_ready(
                            result,
                            guidance,
                            ledger,
                        )
                    )
                else:
                    healthy_ready = healthy_base

                if healthy_ready:
                    healthy = int(ledger.get("healthy_observations", 0)) + 1
                    ledger["healthy_observations"] = healthy
                    changed = True
                    evidence = dict(original)
                    evidence.update(
                        {
                            "pool_state": "ONLINE",
                            "replacement_zfs_state": "ONLINE",
                            "recovery_verified": (
                                healthy >= _REQUIRED_HEALTHY_OBSERVATIONS
                            ),
                            "resilver_state": {
                                "resilver_running": False,
                            },
                        }
                    )
                    repair = self._evaluate(ledger, evidence)
                    ledger["last_session"] = repair
                    ledger["updated_at"] = now
                    if healthy >= _REQUIRED_HEALTHY_OBSERVATIONS:
                        ledger["status"] = "completed"
                        ledger["completed_at"] = now
                else:
                    if ledger.get("healthy_observations") != 0:
                        ledger["healthy_observations"] = 0
                        changed = True
                    ledger["updated_at"] = now

            if changed:
                self._save()

            result["lifeline"] = self.snapshot()
            return result


__all__ = ["LifelineSessionStore"]
