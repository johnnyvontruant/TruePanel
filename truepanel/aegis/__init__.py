"""Project AEGIS reliability intelligence.

AEGIS is an additive, read-only layer over TruePanel's existing detectors,
ORACLE outlooks, Pathfinder recovery contracts, and HoloDeck rehearsals.
"""

from .acceptance import (
    ACCEPTANCE_SCHEMA,
    TRUST_POLICY_SCHEMA,
    acceptance_statement,
    evaluate_acceptance_receipt,
    semantic_sha256,
)
from .assurance import (
    coverage_contract_sha256,
    evaluate_airworthiness,
    load_assurance_envelope,
    validate_repository_evidence,
)
from .attestations import (
    collect_recovery_attestations,
    issue_recovery_attestation,
    reconcile_recovery_attestations,
    validate_recovery_attestation,
)
from .checkride import (
    compose_storage_checkride,
    evaluate_pre_service_clearance,
    run_storage_recovery_rehearsals,
)
from .consequences import correlate_consequences
from .correlation import correlate_incident
from .coverage import coverage_matrix, validate_recovery_coverage
from .coverage_appraisal import (
    APPRAISAL_POLICY_SCHEMA,
    APPRAISAL_SCHEMA,
    appraise_identity_coverage_candidate,
    appraiser_sha256,
    load_identity_appraisal_policy,
)
from .coverage_envelope import (
    COVERAGE_ENVELOPE_DRAFT_SCHEMA,
    prepare_coverage_successor_draft,
)
from .coverage_review import (
    REVIEW_DECISION,
    REVIEW_PACKET_SCHEMA,
    REVIEW_RECEIPT_SCHEMA,
    build_identity_review_packet,
    coverage_review_statement,
    evaluate_identity_review_receipt,
    prepare_identity_review_handoff,
    validate_identity_review_packet,
)
from .evidence_gate import (
    EvidencePromotionPolicy,
    evaluate_evidence_gate,
    validate_field_manifest,
    wilson_interval,
)
from .final_handoff import (
    confirmation_contract_sha256,
    evaluate_final_handoff,
    issue_final_handoff_seal,
)
from .flight_director import run_flight_director_proof
from .identity_coverage import (
    ACCEPTED_IDENTITY_MODES,
    IDENTITY_REQUIRED_CODES,
    build_identity_coverage_candidate,
    evaluate_identity_handoff,
    evaluate_identity_uniqueness,
    rehearse_identity_coverage_contract,
    validate_identity_coverage_candidate,
)
from .passive_providers import (
    TrueNASProtectionEvidenceProvider,
    TrueNASReadOnlyQueryClient,
    TrueNASReplacementInventoryProvider,
    issue_restore_verification_receipt,
)
from .passive_runtime import (
    BoundedTrueNASQueryCache,
    GovernedPassiveEvidenceRuntime,
    GovernedRestoreReceiptStore,
    TrueNASRoleVerifier,
)
from .passive_websocket import (
    GovernedAPIKeyFile,
    GovernedTLSCAFile,
    TrueNASWebSocketReadOnlyClient,
)
from .platform_witness import (
    bind_platform_witness,
    issue_platform_witness,
    normalize_truenas_version,
    validate_platform_witness,
)
from .policy import (
    DEFAULT_CORRELATION_POLICY,
    CorrelationPolicy,
    DeclarativeCorrelationPolicy,
    HypothesisRule,
    validate_correlation_policy,
)
from .promotion_gate import (
    build_promotion_request,
    build_witnessed_promotion_request,
    evaluate_manual_promotion,
)
from .rehearsal import rehearse_recovery_paths
from .reliability import AegisReliabilityEngine
from .requalification import (
    classify_platform_transition,
    envelope_sha256,
    evaluate_successor_envelope,
    renewal_contract_sha256,
    renewal_guidance,
)
from .review_ceremony import (
    REVIEW_BUNDLE_SCHEMA,
    assemble_acceptance_receipt,
    build_review_bundle,
    validate_review_bundle,
)
from .ssh_verifier import (
    DEFAULT_NAMESPACE,
    OpenSshSignatureVerifier,
    validate_allowed_signers_roster,
)
from .stage_witness import witness_validated_stage

__all__ = [
    "ACCEPTANCE_SCHEMA",
    "APPRAISAL_POLICY_SCHEMA",
    "APPRAISAL_SCHEMA",
    "COVERAGE_ENVELOPE_DRAFT_SCHEMA",
    "REVIEW_DECISION",
    "REVIEW_PACKET_SCHEMA",
    "REVIEW_RECEIPT_SCHEMA",
    "AegisReliabilityEngine",
    "ACCEPTED_IDENTITY_MODES",
    "BoundedTrueNASQueryCache",
    "CorrelationPolicy",
    "DEFAULT_CORRELATION_POLICY",
    "DeclarativeCorrelationPolicy",
    "EvidencePromotionPolicy",
    "GovernedAPIKeyFile",
    "GovernedTLSCAFile",
    "HypothesisRule",
    "IDENTITY_REQUIRED_CODES",
    "GovernedPassiveEvidenceRuntime",
    "GovernedRestoreReceiptStore",
    "TrueNASProtectionEvidenceProvider",
    "TrueNASReadOnlyQueryClient",
    "TrueNASReplacementInventoryProvider",
    "TrueNASRoleVerifier",
    "TrueNASWebSocketReadOnlyClient",
    "TRUST_POLICY_SCHEMA",
    "acceptance_statement",
    "appraise_identity_coverage_candidate",
    "appraiser_sha256",
    "bind_platform_witness",
    "build_promotion_request",
    "build_witnessed_promotion_request",
    "build_identity_coverage_candidate",
    "build_identity_review_packet",
    "compose_storage_checkride",
    "collect_recovery_attestations",
    "classify_platform_transition",
    "coverage_contract_sha256",
    "coverage_review_statement",
    "evaluate_airworthiness",
    "evaluate_acceptance_receipt",
    "evaluate_pre_service_clearance",
    "evaluate_manual_promotion",
    "evaluate_identity_handoff",
    "evaluate_identity_uniqueness",
    "evaluate_identity_review_receipt",
    "evaluate_final_handoff",
    "evaluate_successor_envelope",
    "envelope_sha256",
    "issue_recovery_attestation",
    "issue_final_handoff_seal",
    "issue_restore_verification_receipt",
    "issue_platform_witness",
    "load_assurance_envelope",
    "load_identity_appraisal_policy",
    "normalize_truenas_version",
    "prepare_identity_review_handoff",
    "prepare_coverage_successor_draft",
    "correlate_incident",
    "correlate_consequences",
    "coverage_matrix",
    "evaluate_evidence_gate",
    "rehearse_recovery_paths",
    "rehearse_identity_coverage_contract",
    "renewal_contract_sha256",
    "renewal_guidance",
    "run_flight_director_proof",
    "run_storage_recovery_rehearsals",
    "semantic_sha256",
    "confirmation_contract_sha256",
    "reconcile_recovery_attestations",
    "validate_recovery_coverage",
    "validate_identity_coverage_candidate",
    "validate_identity_review_packet",
    "validate_correlation_policy",
    "validate_field_manifest",
    "validate_recovery_attestation",
    "validate_repository_evidence",
    "validate_platform_witness",
    "witness_validated_stage",
    "DEFAULT_NAMESPACE",
    "OpenSshSignatureVerifier",
    "REVIEW_BUNDLE_SCHEMA",
    "assemble_acceptance_receipt",
    "build_review_bundle",
    "validate_allowed_signers_roster",
    "validate_review_bundle",
    "wilson_interval",
]
