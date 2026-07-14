"""
Project Stargate Widget Library.
"""

from truepanel.lab.widgets.progress import ProgressBar
from truepanel.lab.widgets.registry import registry

registry.register(
    "progress",
    ProgressBar,
)

__all__ = [
    "ProgressBar",
    "registry",
]
