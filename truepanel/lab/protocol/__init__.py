from .authorization import (
    PROTOCOL_ARMING_PHRASE,
    ProtocolAuthorization,
)
from .live_runner import ProtocolLiveRunner
from .policy import ProtocolPolicy
from .restore import (
    ProtocolRestorer,
    RestoreResult,
)
from .validator import (
    ProtocolExperimentValidator,
    ValidationReason,
    ValidationResult,
)
"""
Project Stargate protocol-discovery framework.

Protocol experiments describe hypotheses about unknown controller behavior.
They are deliberately separate from the trusted command catalog.
"""

from .archive import ProtocolArchive
from .run import (
    ProtocolRun,
    RunState,
    StepExecution,
)
from .simulator import ProtocolSimulationRunner
from .evidence import (
    EvidenceConfidence,
    EvidenceRecord,
    EvidenceVerdict,
)
from .experiment import (
    ProtocolExperiment,
    ProtocolHypothesis,
)
from .observation import (
    ObservationOutcome,
    ProtocolObservation,
)
from .sequence import (
    ProtocolSequence,
    ProtocolStep,
)

__all__ = [
    "PROTOCOL_ARMING_PHRASE",
    "ProtocolAuthorization",
    "ProtocolExperimentValidator",
    "ProtocolLiveRunner",
    "ProtocolPolicy",
    "ProtocolRestorer",
    "RestoreResult",
    "ValidationReason",
    "ValidationResult",
    "EvidenceConfidence",
    "EvidenceRecord",
    "EvidenceVerdict",
    "ObservationOutcome",
    "ProtocolExperiment",
    "ProtocolHypothesis",
    "ProtocolObservation",
    "ProtocolSequence",
    "ProtocolStep",
]
