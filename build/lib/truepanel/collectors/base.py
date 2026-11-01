"""
Collector Interface

Collectors are responsible for producing a TruePanel state dictionary.
Mission Control should not care whether the state came from TrueNAS,
a simulator, a remote API, or a future plugin.
"""


class Collector:
    name = "collector"

    def update(self):
        raise NotImplementedError("Collectors must implement update()")

