"""Project AEGIS reliability intelligence.

AEGIS is an additive, read-only layer over TruePanel's existing detectors,
ORACLE outlooks, Pathfinder recovery contracts, and HoloDeck rehearsals.
"""

from .correlation import correlate_incident
from .coverage import coverage_matrix, validate_recovery_coverage
from .evidence_gate import (
    EvidencePromotionPolicy,
    evaluate_evidence_gate,
    validate_field_manifest,
    wilson_interval,
)
from .flight_director import run_flight_director_proof
from .policy import (
    DEFAULT_CORRELATION_POLICY,
    CorrelationPolicy,
    DeclarativeCorrelationPolicy,
    HypothesisRule,
    validate_correlation_policy,
)
from .rehearsal import rehearse_recovery_paths
from .reliability import AegisReliabilityEngine

__all__ = [
    "AegisReliabilityEngine",
    "CorrelationPolicy",
    "DEFAULT_CORRELATION_POLICY",
    "DeclarativeCorrelationPolicy",
    "EvidencePromotionPolicy",
    "HypothesisRule",
    "correlate_incident",
    "coverage_matrix",
    "evaluate_evidence_gate",
    "rehearse_recovery_paths",
    "run_flight_director_proof",
    "validate_recovery_coverage",
    "validate_correlation_policy",
    "validate_field_manifest",
    "wilson_interval",
]
