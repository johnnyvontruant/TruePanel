"""Evidence-first incident correlation for Project AEGIS."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from typing import Any

from truepanel.guidance.storage_evidence import normalize_device

from .policy import DEFAULT_CORRELATION_POLICY, CorrelationPolicy

_PRIORITY = {
    "storage.temperature_telemetry_missing": 0,
    "storage.disk_faulted": 1,
    "storage.pool_degraded": 2,
    "storage.smart_warning": 3,
    "cooling.fan_stall": 3,
    "thermal.high_temperature": 4,
    "telemetry.stale": 5,
    "network.link_down": 6,
    "front_panel.lcd_unavailable": 7,
}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _signal_evidence(
    outlook: Mapping[str, Any],
    *,
    matched: set[str] | None = None,
) -> list[dict[str, Any]]:
    results = []
    metrics = _dict(outlook.get("metrics"))
    for key in _list(outlook.get("active_signals")):
        if matched is not None and f"signal:{key}" not in matched:
            continue
        metric = _dict(metrics.get(str(key)))
        if not metric:
            continue
        results.append(
            {
                "source": "ORACLE",
                "signal": str(key),
                "state": metric.get("state"),
                "value": metric.get("value"),
                "baseline": metric.get("baseline_mean"),
                "relative_delta": metric.get("relative_delta"),
                "confidence": metric.get("confidence"),
            }
        )
    return results


def _card_evidence(cards: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence = []
    for card in cards:
        runtime = _dict(card.get("runtime"))
        recovery = _dict(card.get("recovery"))
        evidence.append(
            {
                "source": "verified_detector",
                "signal": _text(card.get("code")),
                "state": _text(recovery.get("state")) or _text(runtime.get("phase")),
                "evidence": deepcopy(_dict(runtime.get("evidence"))),
            }
        )
    return evidence


def _safe_action(cards: list[dict[str, Any]], fallback: str) -> str:
    for card in cards:
        actions = _list(card.get("immediate_actions"))
        for action in actions:
            if not isinstance(action, dict):
                continue
            detail = _text(action.get("detail"))
            if detail:
                return detail
    return fallback


def _verification_state(cards: list[dict[str, Any]]) -> str:
    if not cards:
        return "rehearsed_path_ready"
    statuses = {
        _text(_dict(_dict(card.get("recovery")).get("verification")).get("status"))
        for card in cards
    }
    if statuses == {"passed"}:
        return "passed"
    return "pending"


def _member_identity_tokens(card: Mapping[str, Any]) -> set[str]:
    evidence = _dict(_dict(card.get("runtime")).get("evidence"))
    records = [evidence]
    records.extend(
        item
        for item in _list(evidence.get("missing_members"))
        if isinstance(item, dict)
    )
    tokens: set[str] = set()
    for record in records:
        device = normalize_device(record.get("device") or record.get("drive"))
        if device:
            tokens.add(f"device:{device}")
        bay = record.get("bay") or record.get("physical_bay")
        try:
            parsed_bay = int(bay)
        except (TypeError, ValueError):
            parsed_bay = 0
        if parsed_bay > 0:
            tokens.add(f"bay:{parsed_bay}")
        member = _text(record.get("member_id"))
        if member:
            tokens.add(f"member:{member}")
    return tokens


def _temperature_blind_spot_incident(
    cards: list[dict[str, Any]],
) -> dict[str, Any] | None:
    blind = next(
        (
            card
            for card in cards
            if _text(card.get("code"))
            == "storage.temperature_telemetry_missing"
        ),
        None,
    )
    if blind is None:
        return None
    blind_identity = _member_identity_tokens(blind)
    candidates = [
        card
        for card in cards
        if _text(card.get("code"))
        in {"storage.smart_warning", "storage.disk_faulted"}
        and blind_identity.intersection(_member_identity_tokens(card))
    ]
    if not candidates:
        return None

    related = [blind, candidates[0]]
    shared_identity = sorted(
        blind_identity.intersection(_member_identity_tokens(candidates[0]))
    )
    hard_fault = _text(candidates[0].get("code")) == "storage.disk_faulted"
    return {
        "incident_id": "aegis:drive-temperature-observability",
        "state": "active",
        "likely_cause": "Shared drive-health and telemetry-path degradation",
        "hypothesis": (
            "The same identified storage member has independent health evidence "
            "and no temperature observation. Its temperature remains unknown; "
            "this does not prove overheating."
        ),
        "confidence": 0.90 if hard_fault else 0.84,
        "confidence_basis": {
            "matched_evidence": [
                "alert:storage.temperature_telemetry_missing",
                f"alert:{_text(candidates[0].get('code'))}",
            ],
            "exact_member_identity": shared_identity,
            "temperature_claim": "unknown",
        },
        "supporting_signals": _card_evidence(related),
        "contributing_alerts": [_text(card.get("code")) for card in related],
        "consolidated_alert_count": 1,
        "suppressed_duplicate_count": 1,
        "presentation": {
            "group_by": ["exact_member_identity", "observability_domain"],
            "inhibited_alerts": [_text(candidates[0].get("code"))],
            "raw_alerts_retained": True,
        },
        "safest_next_action": _safe_action(
            [blind],
            "Verify the read-only member identity and restore its temperature collector path.",
        ),
        "verification_state": _verification_state([blind]),
        "verification_scenario": "aegis-drive-temperature-blind-spot",
        "read_only": True,
        "control_authority": False,
    }


def correlate_incident(
    cards: Iterable[dict[str, Any]],
    oracle_outlook: Mapping[str, Any] | None = None,
    *,
    policy: CorrelationPolicy | None = None,
) -> dict[str, Any] | None:
    """Consolidate related evidence into one probable-cause hypothesis.

    The original alerts are never discarded. Their codes and evidence are
    retained as contributing signals so an operator can audit the hypothesis.
    """

    active_cards = [card for card in cards if isinstance(card, dict)]
    active_cards.sort(key=lambda item: _PRIORITY.get(_text(item.get("code")), 99))
    outlook = dict(oracle_outlook or {})
    blind_spot = _temperature_blind_spot_incident(active_cards)
    if blind_spot is not None:
        return blind_spot
    active_policy = policy or DEFAULT_CORRELATION_POLICY
    match = active_policy.evaluate(active_cards, outlook)

    if match is not None:
        matched_keys = set(match.evidence_keys)
        relevant = [
            card
            for card in active_cards
            if _text(card.get("code")) in match.matched_alerts
        ]
        return {
            "incident_id": f"aegis:{match.rule.key}",
            "state": "active",
            "likely_cause": match.rule.likely_cause,
            "hypothesis": match.rule.summary,
            "confidence": match.confidence,
            "confidence_basis": {
                "matched_evidence": list(match.evidence_keys),
                "required_evidence_groups": [list(group) for group in match.rule.evidence_groups],
                "base_confidence": match.rule.base_confidence,
                "confidence_cap": match.rule.confidence_cap,
            },
            "supporting_signals": _signal_evidence(outlook, matched=matched_keys)
            + _card_evidence(relevant),
            "contributing_alerts": list(match.matched_alerts),
            "consolidated_alert_count": 1,
            "suppressed_duplicate_count": len(match.inhibited_alerts),
            "presentation": {
                "group_by": list(match.rule.group_by),
                "inhibited_alerts": list(match.inhibited_alerts),
                "raw_alerts_retained": True,
            },
            "safest_next_action": _safe_action(
                relevant,
                "Reduce avoidable thermal load, check external airflow, and compare fan RPM against PWM effort.",
            ),
            "verification_state": _verification_state(relevant),
            "verification_scenario": match.rule.verification_scenario,
            "read_only": True,
            "control_authority": False,
        }

    if not active_cards:
        return None

    primary = active_cards[0]
    code = _text(primary.get("code"))
    subsystem = code.split(".", 1)[0] if "." in code else "system"
    related = [card for card in active_cards if _text(card.get("code")).startswith(f"{subsystem}.")]
    title = _text(primary.get("title")) or code.replace("_", " ")
    return {
        "incident_id": _text(_dict(primary.get("recovery")).get("incident_id")) or f"aegis:{code}",
        "state": "active",
        "likely_cause": title,
        "hypothesis": _text(primary.get("summary")),
        "confidence": 0.72 if len(related) > 1 else 0.62,
        "confidence_basis": {
            "independent_signals": len(related),
            "correlation_rules": [],
            "hard_alerts": [_text(card.get("code")) for card in related],
        },
        "supporting_signals": _card_evidence(related) + _signal_evidence(outlook),
        "contributing_alerts": [_text(card.get("code")) for card in related],
        "consolidated_alert_count": 1,
        "suppressed_duplicate_count": max(0, len(related) - 1),
        "safest_next_action": _safe_action(related, "Review the verified evidence before taking action."),
        "verification_state": _verification_state(related),
        "read_only": True,
        "control_authority": False,
    }


__all__ = ["correlate_incident"]
