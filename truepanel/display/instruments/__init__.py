"""
TruePanel Flight Deck instrument library.
"""

from .core import (
    Instrument,
    InstrumentGauge,
    InstrumentPage,
    InstrumentProgress,
    InstrumentStatus,
    InstrumentTrend,
)
from .widgets import (
    CapacityWidget,
    DualTrendWidget,
    MetricTrendWidget,
    OperationWidget,
    PerformanceTrendWidget,
    PerformanceWidget,
    ThermalWidget,
)

__all__ = [
    "Instrument",
    "InstrumentGauge",
    "InstrumentPage",
    "InstrumentProgress",
    "InstrumentStatus",
    "InstrumentTrend",
    "CapacityWidget",
    "DualTrendWidget",
    "MetricTrendWidget",
    "OperationWidget",
    "PerformanceTrendWidget",
    "PerformanceWidget",
    "ThermalWidget",
]
