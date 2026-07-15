"""
Protocol-discovery experiment definitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from uuid import uuid4

from .sequence import ProtocolSequence


class ExperimentRisk(str, Enum):
    PASSIVE = "passive"
    DISPLAY_ONLY = "display_only"
    EXPERIMENTAL_WRITE = "experimental_write"
    STATEFUL = "stateful"
    FORBIDDEN = "forbidden"


@dataclass(frozen=True)
class ProtocolHypothesis:
    title: str
    statement: str
    expected_observation: str
    rejection_condition: str = ""

    def __post_init__(self):
        for field_name in (
            "title",
            "statement",
            "expected_observation",
        ):
            value = getattr(self, field_name)

            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} is required"
                )

    def as_dict(self):
        return {
            "title": self.title,
            "statement": self.statement,
            "expected_observation": (
                self.expected_observation
            ),
            "rejection_condition": (
                self.rejection_condition
            ),
        }


@dataclass(frozen=True)
class ProtocolExperiment:
    """
    An immutable protocol hypothesis and its proposed byte sequence.

    This object describes an experiment only. It cannot execute hardware.
    """

    name: str
    hypothesis: ProtocolHypothesis
    sequence: ProtocolSequence
    risk: ExperimentRisk
    controller_family: str = "A125"
    repeat_count: int = 1
    requires_restoration: bool = True
    experiment_id: str = field(
        default_factory=lambda: uuid4().hex
    )

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError(
                "experiment name is required"
            )

        if not isinstance(
            self.hypothesis,
            ProtocolHypothesis,
        ):
            raise TypeError(
                "hypothesis must be a ProtocolHypothesis"
            )

        if not isinstance(
            self.sequence,
            ProtocolSequence,
        ):
            raise TypeError(
                "sequence must be a ProtocolSequence"
            )

        if not isinstance(self.risk, ExperimentRisk):
            raise TypeError(
                "risk must be an ExperimentRisk"
            )

        if self.repeat_count < 1:
            raise ValueError(
                "repeat_count must be at least one"
            )

        if (
            self.requires_restoration
            and not self.sequence.has_restore
        ):
            raise ValueError(
                "restorable experiments require a restore step"
            )

        if self.risk is ExperimentRisk.FORBIDDEN:
            raise ValueError(
                "forbidden experiments cannot be constructed"
            )

    def as_dict(self):
        return {
            "experiment_id": self.experiment_id,
            "name": self.name,
            "controller_family": self.controller_family,
            "risk": self.risk.value,
            "repeat_count": self.repeat_count,
            "requires_restoration": (
                self.requires_restoration
            ),
            "hypothesis": self.hypothesis.as_dict(),
            "sequence": self.sequence.as_dict(),
        }
