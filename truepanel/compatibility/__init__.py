"""
TruePanel passive compatibility survey.
"""

from .checks import collect_compatibility
from .models import CompatibilityCheck, CompatibilityReport
from .report import print_report, run_compatibility

__all__ = [
    "CompatibilityCheck",
    "CompatibilityReport",
    "collect_compatibility",
    "print_report",
    "run_compatibility",
]
