"""
TruePanel passive compatibility survey.
"""

from .checks import collect_compatibility
from .models import CompatibilityCheck, CompatibilityReport
from .report import print_report, run_compatibility
from .support import (
    PRIVACY_CONTRACT,
    SUPPORT_BUNDLE_SCHEMA_VERSION,
    build_support_bundle,
    default_support_path,
    support_bundle_contains_forbidden_keys,
    write_support_bundle,
)

__all__ = [
    "CompatibilityCheck",
    "CompatibilityReport",
    "collect_compatibility",
    "print_report",
    "run_compatibility",
    "PRIVACY_CONTRACT",
    "SUPPORT_BUNDLE_SCHEMA_VERSION",
    "build_support_bundle",
    "default_support_path",
    "support_bundle_contains_forbidden_keys",
    "write_support_bundle",
]
