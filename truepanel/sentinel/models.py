"""Deterministic evidence models for Project SENTINEL.

SENTINEL is deliberately read-only.  These types represent facts TruePanel has
already observed and relationships TruePanel can prove.  They do not grant
control authority and they do not synthesize missing evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class NodeKind(StrEnum):
    """Kinds of objects SENTINEL can relate in the system knowledge graph."""

    HARDWARE = "hardware"
    BAY = "bay"
    DISK = "disk"
    VDEV = "vdev"
    POOL = "pool"
    DATASET = "dataset"
    APPLICATION = "application"
    SERVICE = "service"
    CARGO = "cargo"
    BACKUP_EVIDENCE = "backup_evidence"
    INCIDENT = "incident"
    RECOVERY = "recovery"


class Relation(StrEnum):
    """Directed relationships between graph objects."""

    CONTAINS = "contains"
    MEMBER_OF = "member_of"
    HOSTS = "hosts"
    SERVES = "serves"
    PRODUCES = "produces"
    PROTECTS = "protects"
    AFFECTS = "affects"
    RECOVERS = "recovers"


class ClaimStatus(StrEnum):
    """How strongly the available evidence resolves a statement."""

    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


class Confidence(StrEnum):
    """Bounded confidence vocabulary for deterministic assessments."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    """Traceable evidence supporting a graph object or claim."""

    source: str
    reference: str
    summary: str
    observed_at: float | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source": self.source,
            "reference": self.reference,
            "summary": self.summary,
        }
        if self.observed_at is not None:
            payload["observed_at"] = self.observed_at
        return payload


@dataclass(frozen=True, slots=True)
class KnowledgeNode:
    """A deterministically identified object in the SENTINEL graph."""

    id: str
    kind: NodeKind
    label: str
    state: str | None = None
    attributes: tuple[tuple[str, Any], ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind.value,
            "label": self.label,
            "attributes": dict(self.attributes),
            "evidence": [item.to_payload() for item in self.evidence],
        }
        if self.state is not None:
            payload["state"] = self.state
        return payload


@dataclass(frozen=True, slots=True)
class KnowledgeEdge:
    """A directed, evidence-backed relationship between two graph objects."""

    source: str
    target: str
    relation: Relation
    evidence: tuple[EvidenceRef, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "relation": self.relation.value,
            "evidence": [item.to_payload() for item in self.evidence],
        }


@dataclass(frozen=True, slots=True)
class SentinelClaim:
    """A human-facing statement whose evidence remains inspectable."""

    id: str
    statement: str
    status: ClaimStatus
    confidence: Confidence
    evidence: tuple[EvidenceRef, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "statement": self.statement,
            "status": self.status.value,
            "confidence": self.confidence.value,
            "evidence": [item.to_payload() for item in self.evidence],
        }


@dataclass(slots=True)
class SentinelAssessment:
    """Structured explanation contract for Flight Director and Mission Control."""

    state: str = "CLEAR"
    claims: list[SentinelClaim] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "claims": [claim.to_payload() for claim in self.claims],
            "unknowns": sorted(set(self.unknowns)),
        }
