"""Project AEGIS reliability intelligence.

AEGIS is an additive, read-only layer over TruePanel's existing detectors,
ORACLE outlooks, Pathfinder recovery contracts, and HoloDeck rehearsals.
"""

from .assurance import (
    coverage_contract_sha256,
    evaluate_airworthiness,
    load_assurance_envelope,
    validate_repository_evidence,
)
from .acceptance import (
    ACCEPTANCE_SCHEMA,
    TRUST_POLICY_SCHEMA,
    acceptance_statement,
    evaluate_acceptance_receipt,
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
from .correlation import correlate_incident
from .coverage import coverage_matrix, validate_recovery_coverage
from .evidence_gate import (
    EvidencePromotionPolicy,
    evaluate_evidence_gate,
    validate_field_manifest,
    wilson_interval,
)
from .flight_director import run_flight_director_proof
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
from .rehearsal import rehearse_recovery_paths
from .reliability import AegisReliabilityEngine
from .requalification import (
    classify_platform_transition,
    envelope_sha256,
    evaluate_successor_envelope,
    renewal_contract_sha256,
    renewal_guidance,
)

__all__ = [
    "ACCEPTANCE_SCHEMA",
    "AegisReliabilityEngine",
    "BoundedTrueNASQueryCache",
    "CorrelationPolicy",
    "DEFAULT_CORRELATION_POLICY",
    "DeclarativeCorrelationPolicy",
    "EvidencePromotionPolicy",
    "GovernedAPIKeyFile",
    "GovernedTLSCAFile",
    "HypothesisRule",
    "GovernedPassiveEvidenceRuntime",
    "GovernedRestoreReceiptStore",
    "TrueNASProtectionEvidenceProvider",
    "TrueNASReadOnlyQueryClient",
    "TrueNASReplacementInventoryProvider",
    "TrueNASRoleVerifier",
    "TrueNASWebSocketReadOnlyClient",
    "TRUST_POLICY_SCHEMA",
    "acceptance_statement",
    "bind_platform_witness",
    "compose_storage_checkride",
    "collect_recovery_attestations",
    "classify_platform_transition",
    "coverage_contract_sha256",
    "evaluate_airworthiness",
    "evaluate_acceptance_receipt",
    "evaluate_pre_service_clearance",
    "evaluate_successor_envelope",
    "envelope_sha256",
    "issue_recovery_attestation",
    "issue_restore_verification_receipt",
    "issue_platform_witness",
    "load_assurance_envelope",
    "normalize_truenas_version",
    "correlate_incident",
    "coverage_matrix",
    "evaluate_evidence_gate",
    "rehearse_recovery_paths",
    "renewal_contract_sha256",
    "renewal_guidance",
    "run_flight_director_proof",
    "run_storage_recovery_rehearsals",
    "reconcile_recovery_attestations",
    "validate_recovery_coverage",
    "validate_correlation_policy",
    "validate_field_manifest",
    "validate_recovery_attestation",
    "validate_repository_evidence",
    "validate_platform_witness",
    "wilson_interval",
]
