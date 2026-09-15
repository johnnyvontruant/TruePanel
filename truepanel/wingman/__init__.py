"""Project WINGMAN: grounded, read-only operator assistance."""

from .contracts import GroundingSource, WingmanMode, validate_grounded_answer
from .provider import LlamaCppProvider, WingmanProvider
from .retrieval import rank_sources
from .service import WingmanAdvisoryService, WingmanServiceResult
from .sources import build_status_sources, load_manual_sources

__all__ = [
    "GroundingSource",
    "LlamaCppProvider",
    "WingmanAdvisoryService",
    "WingmanMode",
    "WingmanProvider",
    "WingmanServiceResult",
    "build_status_sources",
    "load_manual_sources",
    "rank_sources",
    "validate_grounded_answer",
]
