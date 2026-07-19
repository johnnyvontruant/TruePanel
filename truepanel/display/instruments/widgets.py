"""
Domain-level Flight Deck widgets.

Widgets translate TruePanel data into reusable InstrumentPage compositions.
They intentionally do not assign Mission Control priorities or alert policy.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from truepanel.display.native_renderer import (
    NativeInstrumentRenderer,
)

from .core import (
    InstrumentGauge,
    InstrumentPage,
    InstrumentProgress,
    InstrumentTrend,
)


def _numeric(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _percentage(value) -> float:
    if isinstance(value, str):
        value = value.strip().rstrip("%")

    return _numeric(value)


def _required_name(value, field_name="name") -> str:
    value = str(value or "").strip()

    if not value:
        raise ValueError(
            f"{field_name} is required"
        )

    return value


@dataclass(frozen=True)
class PerformanceWidget:
    """Two-row CPU and RAM performance panel."""

    cpu_percent: float
    ram_percent: float
    renderer: NativeInstrumentRenderer = field(
        default_factory=NativeInstrumentRenderer,
        compare=False,
        repr=False,
    )

    def page(self) -> InstrumentPage:
        page = InstrumentPage(
            "PERFORMANCE"
        )

        page.add(
            InstrumentGauge(
                "CPU",
                self.cpu_percent,
                renderer=self.renderer,
            )
        )
        page.add(
            InstrumentGauge(
                "RAM",
                self.ram_percent,
                renderer=self.renderer,
            )
        )

        return page

    def render(self):
        return self.page().render()


@dataclass(frozen=True)
class CapacityWidget:
    """Pool-capacity title and usage gauge."""

    pool: str
    percent: float
    renderer: NativeInstrumentRenderer = field(
        default_factory=NativeInstrumentRenderer,
        compare=False,
        repr=False,
    )

    def __post_init__(self):
        _required_name(
            self.pool,
            "pool",
        )

    def page(self) -> InstrumentPage:
        pool = _required_name(
            self.pool,
            "pool",
        )
        percent = _percentage(
            self.percent
        )

        page = InstrumentPage(
            f"POOL {pool[:6]:<6} {round(percent):>3}%"
        )

        page.add(
            InstrumentGauge(
                "USE",
                percent,
                renderer=self.renderer,
            )
        )

        return page

    def render(self):
        return self.page().render()


@dataclass(frozen=True)
class ThermalWidget:
    """Drive-temperature title and normalized thermal gauge."""

    drive: str
    temperature: float
    minimum: float = 20
    maximum: float = 80
    renderer: NativeInstrumentRenderer = field(
        default_factory=NativeInstrumentRenderer,
        compare=False,
        repr=False,
    )

    def __post_init__(self):
        _required_name(
            self.drive,
            "drive",
        )

        if self.maximum <= self.minimum:
            raise ValueError(
                "maximum must be greater than minimum"
            )

    @property
    def normalized_percent(self) -> float:
        temperature = _numeric(
            self.temperature,
            self.minimum,
        )

        return (
            (temperature - self.minimum)
            / (self.maximum - self.minimum)
            * 100
        )

    def page(self) -> InstrumentPage:
        drive = _required_name(
            self.drive,
            "drive",
        )
        temperature = round(
            _numeric(
                self.temperature,
                self.minimum,
            )
        )

        page = InstrumentPage(
            f"TEMP {drive[:5]:<5} {temperature:>2}C"
        )

        page.add(
            InstrumentGauge(
                "TMP",
                self.normalized_percent,
                renderer=self.renderer,
            )
        )

        return page

    def render(self):
        return self.page().render()


@dataclass(frozen=True)
class OperationWidget:
    """Scrub, resilver, or other storage-operation progress panel."""

    operation: str
    percent: float
    renderer: NativeInstrumentRenderer = field(
        default_factory=NativeInstrumentRenderer,
        compare=False,
        repr=False,
    )

    def __post_init__(self):
        _required_name(
            self.operation,
            "operation",
        )

    @property
    def label(self) -> str:
        operation = _required_name(
            self.operation,
            "operation",
        ).upper()

        labels = {
            "SCRUB": "SCR",
            "RESILVER": "RSL",
        }

        return labels.get(
            operation,
            operation[:3],
        )

    def page(self) -> InstrumentPage:
        operation = _required_name(
            self.operation,
            "operation",
        ).upper()

        page = InstrumentPage(
            f"{operation[:10]} ACTIVE"
        )

        page.add(
            InstrumentProgress(
                self.label,
                _percentage(self.percent),
                renderer=self.renderer,
            )
        )

        return page

    def render(self):
        return self.page().render()


def _history(values) -> tuple[float, ...]:
    """
    Normalize a history sequence without changing its scale.

    InstrumentTrend and the native renderer remain responsible for fitting
    values into the available graphical range.
    """

    if values is None:
        return ()

    if isinstance(
        values,
        (str, bytes),
    ):
        raise TypeError(
            "history must be a numeric sequence"
        )

    try:
        return tuple(
            _numeric(value)
            for value in values
        )
    except TypeError as exc:
        raise TypeError(
            "history must be a numeric sequence"
        ) from exc


@dataclass(frozen=True)
class MetricTrendWidget:
    """One titled metric-history panel."""

    title: str
    label: str
    history: tuple[float, ...] | list[float]
    renderer: NativeInstrumentRenderer = field(
        default_factory=NativeInstrumentRenderer,
        compare=False,
        repr=False,
    )

    def __post_init__(self):
        _required_name(
            self.title,
            "title",
        )
        _required_name(
            self.label,
            "label",
        )

        _history(
            self.history
        )

    def page(self) -> InstrumentPage:
        page = InstrumentPage(
            _required_name(
                self.title,
                "title",
            ).upper()
        )

        page.add(
            InstrumentTrend(
                _required_name(
                    self.label,
                    "label",
                ).upper(),
                _history(
                    self.history
                ),
                renderer=self.renderer,
            )
        )

        return page

    def render(self):
        return self.page().render()


@dataclass(frozen=True)
class DualTrendWidget:
    """Two full-width trend rows without a separate title row."""

    first_label: str
    first_history: tuple[float, ...] | list[float]
    second_label: str
    second_history: tuple[float, ...] | list[float]
    renderer: NativeInstrumentRenderer = field(
        default_factory=NativeInstrumentRenderer,
        compare=False,
        repr=False,
    )
    title: str = "TRENDS"

    def __post_init__(self):
        _required_name(
            self.title,
            "title",
        )
        _required_name(
            self.first_label,
            "first_label",
        )
        _required_name(
            self.second_label,
            "second_label",
        )

        _history(
            self.first_history
        )
        _history(
            self.second_history
        )

    def page(self) -> InstrumentPage:
        page = InstrumentPage(
            _required_name(
                self.title,
                "title",
            ).upper()
        )

        page.add(
            InstrumentTrend(
                _required_name(
                    self.first_label,
                    "first_label",
                ).upper(),
                _history(
                    self.first_history
                ),
                renderer=self.renderer,
            )
        )

        page.add(
            InstrumentTrend(
                _required_name(
                    self.second_label,
                    "second_label",
                ).upper(),
                _history(
                    self.second_history
                ),
                renderer=self.renderer,
            )
        )

        return page

    def render(self):
        return self.page().render()


@dataclass(frozen=True)
class PerformanceTrendWidget:
    """CPU and RAM history panel."""

    cpu_history: tuple[float, ...] | list[float]
    ram_history: tuple[float, ...] | list[float]
    renderer: NativeInstrumentRenderer = field(
        default_factory=NativeInstrumentRenderer,
        compare=False,
        repr=False,
    )

    def page(self) -> InstrumentPage:
        return DualTrendWidget(
            first_label="CPU",
            first_history=_history(
                self.cpu_history
            ),
            second_label="RAM",
            second_history=_history(
                self.ram_history
            ),
            renderer=self.renderer,
            title="PERFORMANCE",
        ).page()

    def render(self):
        return self.page().render()


def _history(values) -> tuple[float, ...]:
    """
    Normalize a history sequence without changing its scale.

    InstrumentTrend and the native renderer remain responsible for fitting
    values into the available graphical range.
    """

    if values is None:
        return ()

    if isinstance(
        values,
        (str, bytes),
    ):
        raise TypeError(
            "history must be a numeric sequence"
        )

    try:
        return tuple(
            _numeric(value)
            for value in values
        )
    except TypeError as exc:
        raise TypeError(
            "history must be a numeric sequence"
        ) from exc


@dataclass(frozen=True)
class MetricTrendWidget:
    """One titled metric-history panel."""

    title: str
    label: str
    history: tuple[float, ...] | list[float]
    renderer: NativeInstrumentRenderer = field(
        default_factory=NativeInstrumentRenderer,
        compare=False,
        repr=False,
    )

    def __post_init__(self):
        _required_name(
            self.title,
            "title",
        )
        _required_name(
            self.label,
            "label",
        )

        _history(
            self.history
        )

    def page(self) -> InstrumentPage:
        page = InstrumentPage(
            _required_name(
                self.title,
                "title",
            ).upper()
        )

        page.add(
            InstrumentTrend(
                _required_name(
                    self.label,
                    "label",
                ).upper(),
                _history(
                    self.history
                ),
                renderer=self.renderer,
            )
        )

        return page

    def render(self):
        return self.page().render()


@dataclass(frozen=True)
class DualTrendWidget:
    """Two full-width trend rows without a separate title row."""

    first_label: str
    first_history: tuple[float, ...] | list[float]
    second_label: str
    second_history: tuple[float, ...] | list[float]
    renderer: NativeInstrumentRenderer = field(
        default_factory=NativeInstrumentRenderer,
        compare=False,
        repr=False,
    )
    title: str = "TRENDS"

    def __post_init__(self):
        _required_name(
            self.title,
            "title",
        )
        _required_name(
            self.first_label,
            "first_label",
        )
        _required_name(
            self.second_label,
            "second_label",
        )

        _history(
            self.first_history
        )
        _history(
            self.second_history
        )

    def page(self) -> InstrumentPage:
        page = InstrumentPage(
            _required_name(
                self.title,
                "title",
            ).upper()
        )

        page.add(
            InstrumentTrend(
                _required_name(
                    self.first_label,
                    "first_label",
                ).upper(),
                _history(
                    self.first_history
                ),
                renderer=self.renderer,
            )
        )

        page.add(
            InstrumentTrend(
                _required_name(
                    self.second_label,
                    "second_label",
                ).upper(),
                _history(
                    self.second_history
                ),
                renderer=self.renderer,
            )
        )

        return page

    def render(self):
        return self.page().render()


@dataclass(frozen=True)
class PerformanceTrendWidget:
    """CPU and RAM history panel."""

    cpu_history: tuple[float, ...] | list[float]
    ram_history: tuple[float, ...] | list[float]
    renderer: NativeInstrumentRenderer = field(
        default_factory=NativeInstrumentRenderer,
        compare=False,
        repr=False,
    )

    def page(self) -> InstrumentPage:
        return DualTrendWidget(
            first_label="CPU",
            first_history=_history(
                self.cpu_history
            ),
            second_label="RAM",
            second_history=_history(
                self.ram_history
            ),
            renderer=self.renderer,
            title="PERFORMANCE",
        ).page()

    def render(self):
        return self.page().render()


def _history(values) -> tuple[float, ...]:
    """
    Normalize a history sequence without changing its scale.

    InstrumentTrend and the native renderer remain responsible for fitting
    values into the available graphical range.
    """

    if values is None:
        return ()

    if isinstance(
        values,
        (str, bytes),
    ):
        raise TypeError(
            "history must be a numeric sequence"
        )

    try:
        return tuple(
            _numeric(value)
            for value in values
        )
    except TypeError as exc:
        raise TypeError(
            "history must be a numeric sequence"
        ) from exc


@dataclass(frozen=True)
class MetricTrendWidget:
    """One titled metric-history panel."""

    title: str
    label: str
    history: tuple[float, ...] | list[float]
    renderer: NativeInstrumentRenderer = field(
        default_factory=NativeInstrumentRenderer,
        compare=False,
        repr=False,
    )

    def __post_init__(self):
        _required_name(
            self.title,
            "title",
        )
        _required_name(
            self.label,
            "label",
        )

        _history(
            self.history
        )

    def page(self) -> InstrumentPage:
        page = InstrumentPage(
            _required_name(
                self.title,
                "title",
            ).upper()
        )

        page.add(
            InstrumentTrend(
                _required_name(
                    self.label,
                    "label",
                ).upper(),
                _history(
                    self.history
                ),
                renderer=self.renderer,
            )
        )

        return page

    def render(self):
        return self.page().render()


@dataclass(frozen=True)
class DualTrendWidget:
    """Two full-width trend rows without a separate title row."""

    first_label: str
    first_history: tuple[float, ...] | list[float]
    second_label: str
    second_history: tuple[float, ...] | list[float]
    renderer: NativeInstrumentRenderer = field(
        default_factory=NativeInstrumentRenderer,
        compare=False,
        repr=False,
    )
    title: str = "TRENDS"

    def __post_init__(self):
        _required_name(
            self.title,
            "title",
        )
        _required_name(
            self.first_label,
            "first_label",
        )
        _required_name(
            self.second_label,
            "second_label",
        )

        _history(
            self.first_history
        )
        _history(
            self.second_history
        )

    def page(self) -> InstrumentPage:
        page = InstrumentPage(
            _required_name(
                self.title,
                "title",
            ).upper()
        )

        page.add(
            InstrumentTrend(
                _required_name(
                    self.first_label,
                    "first_label",
                ).upper(),
                _history(
                    self.first_history
                ),
                renderer=self.renderer,
            )
        )

        page.add(
            InstrumentTrend(
                _required_name(
                    self.second_label,
                    "second_label",
                ).upper(),
                _history(
                    self.second_history
                ),
                renderer=self.renderer,
            )
        )

        return page

    def render(self):
        return self.page().render()


@dataclass(frozen=True)
class PerformanceTrendWidget:
    """CPU and RAM history panel."""

    cpu_history: tuple[float, ...] | list[float]
    ram_history: tuple[float, ...] | list[float]
    renderer: NativeInstrumentRenderer = field(
        default_factory=NativeInstrumentRenderer,
        compare=False,
        repr=False,
    )

    def page(self) -> InstrumentPage:
        return DualTrendWidget(
            first_label="CPU",
            first_history=_history(
                self.cpu_history
            ),
            second_label="RAM",
            second_history=_history(
                self.ram_history
            ),
            renderer=self.renderer,
            title="PERFORMANCE",
        ).page()

    def render(self):
        return self.page().render()
