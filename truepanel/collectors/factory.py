"""
Collector Factory
"""


def create_collector(kind="truenas", scenario="normal"):
    if kind == "simulator":
        from .simulator import SimulatorCollector

        return SimulatorCollector(scenario=scenario)

    from collector import TruePanelCollector

    return TruePanelCollector()
