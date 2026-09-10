from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from truepanel.aegis.assurance import load_assurance_envelope
from truepanel.aegis.coverage import coverage_matrix
from truepanel.aegis.passive_runtime import BoundedTrueNASQueryCache
from truepanel.aegis.platform_witness import (
    bind_platform_witness,
    issue_platform_witness,
)
from truepanel.aegis.policy import DEFAULT_CORRELATION_POLICY
from truepanel.aegis.rehearsal import rehearse_recovery_paths
from truepanel.aegis.requalification import (
    classify_platform_transition,
    envelope_sha256,
    evaluate_successor_envelope,
    renewal_contract_sha256,
    renewal_guidance,
)
from truepanel.holodeck.aegis_requalification import run_requalification_rehearsal

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC).timestamp()
ROOT = Path(__file__).parents[1] / "truepanel"


class Client:
    def __init__(self, version: str):
        self.version = version

    def call(self, _method, *_arguments):
        return f"TrueNAS-SCALE-{self.version}"


def payload(version: str):
    witness = issue_platform_witness(
        BoundedTrueNASQueryCache(Client(version)), clock=lambda: NOW
    )
    return bind_platform_witness({"system": {}}, witness)


def candidate(version: str = "25.10.6"):
    accepted = load_assurance_envelope()
    result = deepcopy(accepted)
    result.update(
        {
            "envelope_id": "aegis-airworthiness-upgrade-rehearsal-v3",
            "predecessor_envelope_sha256": envelope_sha256(accepted),
            "issued_at": "2026-09-06T04:08:19Z",
            "expires_at": "2026-12-05T04:08:19Z",
            "platform_version": version,
            "review_required": True,
            "automatic_acceptance": False,
            "renewal_contract_sha256": renewal_contract_sha256(ROOT),
        }
    )
    return result


def evaluate(value=None, *, version="25.10.6"):
    return evaluate_successor_envelope(
        accepted=load_assurance_envelope(),
        candidate=value or candidate(version),
        payload=payload(version),
        coverage_matrix=coverage_matrix(rehearse_recovery_paths()),
        correlation_policy=DEFAULT_CORRELATION_POLICY.describe(),
        now=NOW,
        package_root=ROOT,
    )


def test_coherent_successor_is_review_ready_but_never_accepted():
    result = evaluate()

    assert result["status"] == "READY_FOR_OPERATOR_REVIEW"
    assert result["transition"] == "UPGRADE"
    assert result["candidate_appraisal"]["status"] == "CURRENT"
    assert result["review_required"] is True
    assert result["automatic_acceptance"] is False
    assert result["candidate_installed"] is False
    assert result["runtime_writes"] == 0
    assert result["control_authority"] is False


def test_lineage_downgrade_expiry_and_automatic_acceptance_hold():
    wrong_parent = candidate()
    wrong_parent["predecessor_envelope_sha256"] = "0" * 64
    assert evaluate(wrong_parent)["reason"] == "PredecessorMismatch"

    downgrade = candidate("25.10.4")
    assert evaluate(downgrade, version="25.10.4")["reason"] == "PlatformDowngrade"

    too_long = candidate()
    too_long["expires_at"] = "2027-09-06T04:08:19Z"
    assert evaluate(too_long)["reason"] == "ValidityWindowInvalid"

    automatic = candidate()
    automatic["automatic_acceptance"] = True
    assert evaluate(automatic)["reason"] == "AutomaticAcceptanceForbidden"


def test_unknown_prerelease_order_requires_review_not_a_guess():
    proposal = candidate("25.10-RC.1")
    result = evaluate(proposal, version="25.10-RC.1")

    assert result["status"] == "REVIEW"
    assert result["reason"] == "PlatformOrderingRequiresReview"


def test_transition_classifier_and_guidance_are_explicit():
    assert classify_platform_transition("25.10.5", "25.10.6") == "UPGRADE"
    assert classify_platform_transition("25.10.5", "25.10.4") == "DOWNGRADE"
    assert classify_platform_transition("25.10.5", "25.10-RC.1") == "UNSUPPORTED"

    guidance = renewal_guidance({"status": "HOLD", "reason": "PlatformDrift"})
    assert guidance["state"] == "REQUALIFICATION_REQUIRED"
    assert guidance["automatic_acceptance"] is False
    assert guidance["control_authority"] is False


def test_holodeck_rehearsal_has_no_false_review_ready_paths():
    report = run_requalification_rehearsal()

    assert report["old_envelope_after_upgrade"] == {
        "status": "HOLD",
        "reason": "PlatformDrift",
    }
    assert report["status_counts"] == {
        "READY_FOR_OPERATOR_REVIEW": 2,
        "REVIEW": 2,
        "HOLD": 6,
    }
    assert report["measurements"]["false_review_ready_paths"] == 0
    assert report["measurements"]["candidate_installations"] == 0
    assert report["measurements"]["automatic_acceptances"] == 0
    assert report["production_mutation"] is False
    assert report["control_authority"] is False
