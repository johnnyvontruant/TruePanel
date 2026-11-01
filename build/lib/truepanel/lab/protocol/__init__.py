from .glyph_experiment import (
    build_glyph_upload_experiment,
)
from .glyph_library import (
    GLYPHS,
    VERTICAL_FILL_GLYPHS,
    all_glyphs,
    glyph,
    vertical_fill_level,
)
from .glyph_upload import (
    CandidateGlyphSerializer,
    GlyphPayloadLayout,
    GlyphUploadPlan,
)
from .glyphs import (
    CustomGlyph,
    GLYPH_HEIGHT,
    GLYPH_WIDTH,
)
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
    "CandidateGlyphSerializer",
    "CustomGlyph",
    "GLYPHS",
    "GLYPH_HEIGHT",
    "GLYPH_WIDTH",
    "GlyphPayloadLayout",
    "GlyphUploadPlan",
    "VERTICAL_FILL_GLYPHS",
    "all_glyphs",
    "build_glyph_upload_experiment",
    "glyph",
    "vertical_fill_level",
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
