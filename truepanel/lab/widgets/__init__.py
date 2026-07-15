"""
Project Stargate Widget Library.
"""

from truepanel.lab.widgets.progress import ProgressBar
from truepanel.lab.widgets.registry import registry
from truepanel.lab.widgets.thermometer import Thermometer
from truepanel.lab.widgets.signal import SignalMeter
from truepanel.lab.widgets.battery import BatteryMeter
from truepanel.lab.widgets.spinner import Spinner
from truepanel.lab.widgets.sparkline import Sparkline

registry.register(
    "sparkline",
    Sparkline,
)

registry.register(
    "spinner",
    Spinner,
)

registry.register(
    "battery",
    BatteryMeter,
)
registry.register(
    "signal",
    SignalMeter,
)
registry.register(
    "thermometer",
    Thermometer,
)
registry.register(
    "progress",
    ProgressBar,
)

__all__ = [
    "ProgressBar",
    "registry",
    "Thermometer",
    "SignalMeter",
    "BatteryMeter",
    "Spinner",
    "Sparkline",
]
