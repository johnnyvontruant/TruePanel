"""
Collector Factory
"""

from truepanel.plugins import load_plugins


def create_collector(kind="truenas", scenario="normal", registry=None):
    if registry is None:
        registry = load_plugins()

    if kind in registry.collectors:
        return registry.collectors[kind](scenario=scenario)

    from collector import TruePanelCollector

    return TruePanelCollector()
