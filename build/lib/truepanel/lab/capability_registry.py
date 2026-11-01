"""
Project Stargate Capability Evidence Registry.

Stores capability evidence gathered from laboratory observations.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CapabilityEvidence:
    """One observation supporting a capability."""

    source: str
    confidence: float
    detail: str = ""


@dataclass
class CapabilityRecord:
    """Evidence collected for one capability."""

    name: str
    evidence: list[CapabilityEvidence] = field(
        default_factory=list
    )

    def add(
        self,
        evidence: CapabilityEvidence,
    ) -> None:
        self.evidence.append(evidence)

    @property
    def confidence(self) -> float:
        if not self.evidence:
            return 0.0

        return max(
            item.confidence
            for item in self.evidence
        )

    @property
    def observed(self) -> bool:
        return bool(self.evidence)


class CapabilityRegistry:
    """Stores evidence for laboratory capabilities."""

    def __init__(self):
        self._records: dict[
            str,
            CapabilityRecord,
        ] = {}

    def record(
        self,
        capability: str,
        evidence: CapabilityEvidence,
    ) -> None:
        if capability not in self._records:
            self._records[capability] = (
                CapabilityRecord(capability)
            )

        self._records[capability].add(evidence)

    def get(
        self,
        capability: str,
    ) -> CapabilityRecord:
        return self._records.get(
            capability,
            CapabilityRecord(capability),
        )

    def capabilities(self) -> list[str]:
        return sorted(self._records)

    def as_dict(self) -> dict[str, object]:
        return {
            name: {
                "confidence": record.confidence,
                "observed": record.observed,
                "evidence": [
                    {
                        "source": e.source,
                        "confidence": e.confidence,
                        "detail": e.detail,
                    }
                    for e in record.evidence
                ],
            }
            for name, record in sorted(
                self._records.items()
            )
        }
