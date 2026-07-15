"""
TruePanel hardware support.
"""

from .buzzer import Buzzer

__all__ = ["Buzzer"]

from .a125 import A125Capabilities, A125Controller
