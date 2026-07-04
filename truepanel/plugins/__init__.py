"""
TruePanel Plugin System
"""

from .manager import load_plugins
from .registry import Registry

__all__ = ["Registry", "load_plugins"]
