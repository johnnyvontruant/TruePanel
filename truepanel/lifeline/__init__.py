"""Project Lifeline guided-repair primitives."""

from .fingerprint import (
    DEFAULT_DRIVE_FINGERPRINT_PATH,
    DriveFingerprintProvider,
    DriveFingerprintStore,
)
from .identify import (
    BayIdentificationService,
    DEFAULT_IDENTIFY_SECONDS,
    MAX_IDENTIFY_SECONDS,
)
from .profiles import (
    QNAP_TVS_X71,
    ServiceProfile,
    profile_keys,
    service_profile,
    service_profile_for_config,
)
from .replacement import ReplacementCandidateProvider, parse_block_signatures
from .runtime import attach_repair_sessions
from .session import (
    DRIVE_PHASES,
    RepairGate,
    RepairSession,
    ReplacementAssessment,
    evaluate_drive_repair,
)
from .store import DEFAULT_LIFELINE_PATH, LifelineSessionStore

__all__ = [
    "BayIdentificationService",
    "DEFAULT_DRIVE_FINGERPRINT_PATH",
    "DEFAULT_IDENTIFY_SECONDS",
    "DEFAULT_LIFELINE_PATH",
    "DRIVE_PHASES",
    "DriveFingerprintProvider",
    "DriveFingerprintStore",
    "LifelineSessionStore",
    "MAX_IDENTIFY_SECONDS",
    "QNAP_TVS_X71",
    "RepairGate",
    "RepairSession",
    "ReplacementAssessment",
    "ReplacementCandidateProvider",
    "ServiceProfile",
    "attach_repair_sessions",
    "evaluate_drive_repair",
    "parse_block_signatures",
    "profile_keys",
    "service_profile",
    "service_profile_for_config",
]
