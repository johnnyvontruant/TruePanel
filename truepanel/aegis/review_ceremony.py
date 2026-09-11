"""Portable, content-addressed packets for independent AEGIS review."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .acceptance import (
    ACCEPTANCE_SCHEMA,
    TRUST_POLICY_SCHEMA,
    acceptance_statement,
    semantic_sha256,
)

REVIEW_BUNDLE_SCHEMA = "truepanel.aegis-review-bundle/v1"


def build_review_bundle(
    *,
    receipt: Mapping[str, Any],
    candidate: Mapping[str, Any],
    appraisal: Mapping[str, Any],
    predecessor: Mapping[str, Any],
    promotion_request: Mapping[str, Any],
    trust_policy: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the exact public packet each independent reviewer inspects."""

    unsigned = dict(receipt)
    unsigned["signatures"] = []
    statement = acceptance_statement(unsigned)
    return {
        "schema": REVIEW_BUNDLE_SCHEMA,
        "statement": statement,
        "subjects": {
            "candidate": dict(candidate),
            "appraisal": dict(appraisal),
            "predecessor": dict(predecessor),
            "promotion_request": dict(promotion_request),
        },
        "trust_policy": dict(trust_policy),
        "statement_sha256": semantic_sha256(statement),
        "trust_policy_sha256": semantic_sha256(trust_policy),
        "private_key_material": False,
        "signing_authority": False,
        "promotion_authority": False,
    }


def validate_review_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Fail closed unless presentation, subjects, policy, and statement agree."""

    failures: list[str] = []
    expected_bundle_fields = {
        "schema",
        "statement",
        "subjects",
        "trust_policy",
        "statement_sha256",
        "trust_policy_sha256",
        "private_key_material",
        "signing_authority",
        "promotion_authority",
    }
    if set(bundle) != expected_bundle_fields:
        failures.append("ReviewBundleFieldsInvalid")
    if any(
        bundle.get(field) is not False
        for field in (
            "private_key_material",
            "signing_authority",
            "promotion_authority",
        )
    ):
        failures.append("ReviewBundleAuthorityInvalid")
    statement = bundle.get("statement")
    subjects = bundle.get("subjects")
    policy = bundle.get("trust_policy")
    if bundle.get("schema") != REVIEW_BUNDLE_SCHEMA:
        failures.append("ReviewBundleSchemaInvalid")
    if (
        not isinstance(statement, Mapping)
        or statement.get("schema") != ACCEPTANCE_SCHEMA
    ):
        failures.append("ReviewStatementInvalid")
    if not isinstance(subjects, Mapping):
        failures.append("ReviewSubjectsInvalid")
        subjects = {}
    elif set(subjects) != {
        "candidate",
        "appraisal",
        "predecessor",
        "promotion_request",
    }:
        failures.append("ReviewSubjectFieldsInvalid")
    if not isinstance(policy, Mapping) or policy.get("schema") != TRUST_POLICY_SCHEMA:
        failures.append("ReviewTrustPolicyInvalid")
        policy = {}
    bindings = {
        "candidate": "candidate_envelope_sha256",
        "appraisal": "appraisal_sha256",
        "predecessor": "predecessor_envelope_sha256",
        "promotion_request": "promotion_request_sha256",
    }
    if isinstance(statement, Mapping):
        if set(statement) != set(acceptance_statement(statement)):
            failures.append("ReviewStatementFieldsInvalid")
        for subject_name, digest_name in bindings.items():
            subject = subjects.get(subject_name)
            if not isinstance(subject, Mapping) or statement.get(
                digest_name
            ) != semantic_sha256(subject):
                failures.append(
                    f"{subject_name.title().replace('_', '')}BindingInvalid"
                )
        if bundle.get("statement_sha256") != semantic_sha256(statement):
            failures.append("ReviewStatementDigestInvalid")
    if bundle.get("trust_policy_sha256") != semantic_sha256(policy):
        failures.append("ReviewTrustPolicyDigestInvalid")
    keys = policy.get("keys") if isinstance(policy, Mapping) else None
    threshold = policy.get("threshold") if isinstance(policy, Mapping) else None
    identities = (
        [
            (str(item.get("key_id") or ""), str(item.get("reviewer_id") or ""))
            for item in keys or []
            if isinstance(item, Mapping)
        ]
        if isinstance(keys, Sequence) and not isinstance(keys, (str, bytes))
        else []
    )
    if (
        not isinstance(threshold, int)
        or isinstance(threshold, bool)
        or threshold < 2
        or len({item[0] for item in identities if item[0]}) < threshold
        or len({item[1] for item in identities if item[1]}) < threshold
    ):
        failures.append("ReviewSeparationOfDutyInvalid")
    return {
        "status": "READY_FOR_INDEPENDENT_SIGNATURES" if not failures else "HOLD",
        "reason": "ReviewBundleBound" if not failures else failures[0],
        "failures": failures,
        "bundle_sha256": semantic_sha256(bundle),
        "signing_authority": False,
        "promotion_authority": False,
    }


def assemble_acceptance_receipt(
    bundle: Mapping[str, Any], signatures: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Attach detached public signatures without signing or accepting anything."""

    validation = validate_review_bundle(bundle)
    if validation["status"] != "READY_FOR_INDEPENDENT_SIGNATURES":
        raise ValueError(validation["reason"])
    statement = bundle["statement"]
    receipt = dict(statement)
    receipt["signatures"] = [dict(item) for item in signatures]
    return receipt


__all__ = [
    "REVIEW_BUNDLE_SCHEMA",
    "assemble_acceptance_receipt",
    "build_review_bundle",
    "validate_review_bundle",
]
