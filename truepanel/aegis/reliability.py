"""Mission Control composition service for Project AEGIS."""

from __future__ import annotations

import math
from copy import deepcopy
from statistics import fmean
from threading import Lock
from typing import Any

from truepanel.oracle import OracleEngine

from .assurance import evaluate_airworthiness
from .checkride import compose_storage_checkride
from .correlation import correlate_incident
from .coverage import coverage_matrix
from .flight_director import run_flight_director_proof
from .policy import DEFAULT_CORRELATION_POLICY, CorrelationPolicy
from .rehearsal import rehearse_recovery_paths


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _average(values: list[float]) -> float | None:
    return fmean(values) if values else None


class AegisReliabilityEngine:
    """Add predictive outlook, incident correlation, and coverage evidence.

    Mission Control is a threaded HTTP service and several dashboard surfaces
    may read the same status endpoint. ORACLE therefore samples on a bounded
    telemetry cadence rather than once per browser request. Correlation still
    re-evaluates every request so a verified hard alert is presented
    immediately without training duplicate reads into the learned baseline.
    """

    def __init__(
        self,
        *,
        oracle: OracleEngine | None = None,
        correlation_policy: CorrelationPolicy | None = None,
        protection_evidence_provider: Any | None = None,
        sample_interval_seconds: float = 5.0,
    ) -> None:
        interval = _number(sample_interval_seconds)
        if interval is None or interval <= 0:
            raise ValueError("AEGIS sample interval must be finite and positive")

        self.oracle = oracle or OracleEngine()
        self.correlation_policy = correlation_policy or DEFAULT_CORRELATION_POLICY
        self.protection_evidence_provider = protection_evidence_provider
        self.sample_interval_seconds = interval
        self.rehearsals = rehearse_recovery_paths()
        self.matrix = coverage_matrix(self.rehearsals)
        proof = run_flight_director_proof()
        self.flight_director = {
            "scenario": proof["scenario"],
            "simulation": True,
            "field_validated": False,
            "control_authority": False,
            # This proof is a packaged HoloDeck reference scenario, not a
            # diagnosis of whichever incident happens to be active live.
            # Presentation must fail closed until a future Flight Director
            # result explicitly binds itself to an incident ID.
            "presentation_scope": "reference_rehearsal",
            "evidence_maturity": "deterministic_lab_fixture",
            "incident_id": None,
            "applies_to_active_incident": False,
            "incident": proof["active_incident"],
            "timeline": proof["incident_time_machine"]["landmarks"],
            "topology": proof["causal_hardware_map"],
            "forecast": proof["safe_operating_envelope"],
            "rehearsals": proof["what_if_rehearsals"],
            "recovery_plan": proof["recovery_flight_plan"],
            "verification": proof["repair_verification_signature"],
            "measurements": proof["measurements"],
            "evidence_sha256": proof["evidence_sha256"],
        }
        self._sequence = 0
        self._last_sample_timestamp: float | None = None
        self._last_outlook: dict[str, Any] | None = None
        self._sample_lock = Lock()

    @staticmethod
    def _metrics(payload: dict[str, Any]) -> dict[str, float]:
        metrics: dict[str, float] = {}
        fans = _dict(payload.get("fans"))
        channels = [item for item in _list(fans.get("channels")) if isinstance(item, dict)]
        monitored = [item for item in channels if item.get("monitored") is True] or channels
        rpm = [value for item in monitored if (value := _number(item.get("rpm"))) is not None]
        pwm = [
            value
            for item in monitored
            if (value := _number(item.get("pwm"))) is not None and value > 0
        ]
        if (value := _average(rpm)) is not None:
            metrics["fan.rpm"] = value
        if (value := _average(pwm)) is not None:
            metrics["fan.pwm"] = value

        storage = _dict(payload.get("storage"))
        drive_temperatures = []
        for item in _list(storage.get("temperatures")):
            if not isinstance(item, dict):
                continue
            value = _number(item.get("temperature_c", item.get("temp")))
            if value is not None:
                drive_temperatures.append(value)
        if drive_temperatures:
            metrics["drive.temperature_c"] = max(drive_temperatures)

        reallocated = []
        for item in _list(storage.get("smart")):
            if not isinstance(item, dict):
                continue
            value = _number(item.get("reallocated"))
            if value is not None:
                reallocated.append(value)
        if reallocated:
            metrics["drive.smart_reallocated"] = max(reallocated)

        control = _dict(fans.get("control"))
        hottest = _number(control.get("thermal_hottest_temperature_c"))
        if hottest is not None:
            metrics["cpu.temperature_c"] = hottest

        primary = next(
            (
                item
                for item in _list(payload.get("network"))
                if isinstance(item, dict) and item.get("primary") is True
            ),
            None,
        )
        if primary:
            speed = _number(primary.get("speed_mbps", primary.get("link_mbps")))
            errors = _number(primary.get("errors"))
            if speed is not None:
                metrics["network.link_mbps"] = speed
            if errors is not None:
                metrics["network.errors"] = errors
        return metrics

    @staticmethod
    def _hard_faults(cards: list[dict[str, Any]]) -> tuple[str, ...]:
        codes = {str(card.get("code") or "") for card in cards}
        hard = set()
        if "cooling.fan_stall" in codes:
            hard.add("fan.rpm")
        if "thermal.high_temperature" in codes:
            hard.update(("drive.temperature_c", "cpu.temperature_c"))
        if "network.link_down" in codes:
            hard.add("network.link_mbps")
        if codes & {"storage.smart_warning", "storage.disk_faulted"}:
            hard.add("drive.smart_reallocated")
        return tuple(hard)

    def _observe_oracle(
        self,
        *,
        source_timestamp: float | None,
        metrics: dict[str, float],
        hard_faults: tuple[str, ...],
    ) -> tuple[dict[str, Any], float, bool]:
        with self._sample_lock:
            self._sequence += 1
            timestamp = source_timestamp
            if timestamp is None:
                if self._last_sample_timestamp is None:
                    timestamp = float(self._sequence) * self.sample_interval_seconds
                else:
                    timestamp = (
                        self._last_sample_timestamp + self.sample_interval_seconds
                    )

            fresh = (
                self._last_outlook is None
                or self._last_sample_timestamp is None
                or timestamp - self._last_sample_timestamp
                >= self.sample_interval_seconds
            )
            if fresh:
                self._last_outlook = self.oracle.observe(
                    timestamp=timestamp,
                    metrics=metrics,
                    hard_faults=hard_faults,
                )
                self._last_sample_timestamp = timestamp

            return (
                deepcopy(self._last_outlook or {}),
                float(self._last_sample_timestamp or timestamp),
                fresh,
            )

    @staticmethod
    def _topology(payload: dict[str, Any]) -> dict[str, Any]:
        """Summarize physical-topology evidence available this sample.

        This never invents a bay: a drive that could not be resolved to a
        physical bay by :mod:`truepanel.hardware.drive_localization` is
        reported as ``hottest_drive_bay: None`` and
        ``hottest_drive_localized: False`` rather than guessed, matching the
        project's existing rule that uncertainty must be preserved, not
        hidden, when topology evidence is incomplete.
        """

        storage = _dict(payload.get("storage"))
        entries = [
            item for item in _list(storage.get("temperatures")) if isinstance(item, dict)
        ]

        hottest: dict[str, Any] | None = None
        hottest_value: float | None = None
        for item in entries:
            value = _number(item.get("temperature_c", item.get("temp")))
            if value is None:
                continue
            if hottest_value is None or value > hottest_value:
                hottest_value = value
                hottest = item

        bay = hottest.get("bay") if hottest else None
        known_bays = sum(1 for item in entries if item.get("bay") is not None)

        return {
            "hottest_drive_temperature_c": hottest_value,
            "hottest_drive_bay": bay,
            "hottest_drive_localized": bay is not None,
            "drives_with_known_bay": known_bays,
            "drives_observed": len(entries),
        }

    def observe(self, payload: dict[str, Any]) -> dict[str, Any]:
        source_timestamp = _number(payload.get("timestamp"))
        cards = [
            item
            for item in _list(payload.get("operator_guidance"))
            if isinstance(item, dict)
        ]
        metrics = self._metrics(payload)
        outlook, sampled_at, fresh = self._observe_oracle(
            source_timestamp=source_timestamp,
            metrics=metrics,
            hard_faults=self._hard_faults(cards),
        )
        incident = correlate_incident(cards, outlook, policy=self.correlation_policy)
        working_payload = payload
        passive_evidence = None
        if incident and self.protection_evidence_provider is not None:
            try:
                passive_evidence = self.protection_evidence_provider.observe(
                    incident_id=str(incident.get("incident_id") or "")
                )
            except (OSError, RuntimeError, TypeError, ValueError, AttributeError):
                passive_evidence = {
                    "read_only": True,
                    "control_authority": False,
                    "restore_verified": False,
                    "hold_reason": "passive evidence provider unavailable",
                }
            backup_context = _dict(_dict(passive_evidence).get("backup_context"))
            if backup_context:
                working_payload = deepcopy(payload)
                working_payload["backup_context"] = backup_context
        active_flight_director = compose_storage_checkride(working_payload, incident)
        policy_description = self.correlation_policy.describe()
        airworthiness = evaluate_airworthiness(
            payload=working_payload,
            coverage_matrix=self.matrix,
            correlation_policy=policy_description,
        )
        return {
            "schema_version": 1,
            "project": "AEGIS",
            "read_only": True,
            "production_mutation": False,
            "state": "INCIDENT" if incident else outlook.get("state", "NORMAL"),
            "active_incident": incident,
            "oracle": outlook,
            "sampling": {
                "sampled_at": sampled_at,
                "source_timestamp": source_timestamp,
                "fresh_sample": fresh,
                "minimum_interval_seconds": self.sample_interval_seconds,
                "request_count": self._sequence,
            },
            "coverage_matrix": self.matrix,
            "correlation_policy": policy_description,
            "coverage_summary": {
                "total": self.matrix["total"],
                "trusted": self.matrix["trusted"],
                "gaps": self.matrix["gaps"],
            },
            "topology": self._topology(payload),
            "passive_evidence": passive_evidence,
            "airworthiness": airworthiness,
            "flight_director": active_flight_director or self.flight_director,
        }


__all__ = ["AegisReliabilityEngine"]
