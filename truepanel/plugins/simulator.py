"""
Simulator Plugin
"""

from .base import Plugin
from truepanel.collectors.simulator import SimulatorCollector


class SimulatorPlugin(Plugin):
    name = "Simulator"
    version = "1.0"
    author = "TruePanel"

    def register(self, registry):
        registry.register_collector(
            "simulator",
            lambda scenario="normal": SimulatorCollector(scenario=scenario),
        )
