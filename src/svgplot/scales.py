"""Data-domain to pixel-space scales.

Linear, categorical, and time scales plus "nice" tick generation. Datetime
x-values are handled here as a scale option rather than a separate chart
type (see docs/research/10-feature-matrix.md, "시간축 선"). Kept as a single
file until a concrete need for additional scale types (e.g. log) appears.

Tick generation deliberately avoids any text-width measurement (no font
renderer in pure SVG, see docs/research/12-aesthetics.md §3) — "nice" here
means round numbers/round time steps, not "however many fit visually".
"""

from __future__ import annotations

import math
from datetime import datetime


class LinearScale:
    """Maps a numeric data domain to a pixel range."""

    def __init__(self, domain: tuple[float, float], range_: tuple[float, float]) -> None:
        self.domain = domain
        self.range = range_

    def __call__(self, value: float) -> float:
        """Map a data value to a pixel position."""
        domain_min, domain_max = self.domain
        range_min, range_max = self.range
        if domain_max == domain_min:
            return (range_min + range_max) / 2
        ratio = (value - domain_min) / (domain_max - domain_min)
        return range_min + ratio * (range_max - range_min)


class CategoricalScale:
    """Maps discrete category values to evenly spaced pixel bands (d3's ``scaleBand``).

    ``scale(category)`` gives a band's start position; ``scale.center(category)``
    gives its midpoint (what most callers actually want, e.g. for tick labels);
    ``scale.bandwidth`` gives each band's width (e.g. for bar width).
    """

    def __init__(self, categories: list[str], range_: tuple[float, float]) -> None:
        self.categories = list(categories)
        self.range = range_
        self._index_by_category = {category: index for index, category in enumerate(self.categories)}

    @property
    def bandwidth(self) -> float:
        if not self.categories:
            return 0.0
        range_min, range_max = self.range
        return (range_max - range_min) / len(self.categories)

    def __call__(self, category: str) -> float:
        """Map a category to its band's start position."""
        if category not in self._index_by_category:
            raise KeyError(f"category not found in scale: {category!r}")
        range_min, _ = self.range
        return range_min + self._index_by_category[category] * self.bandwidth

    def center(self, category: str) -> float:
        """Map a category to its band's midpoint."""
        return self(category) + self.bandwidth / 2


class TimeScale:
    """Maps a datetime domain to a pixel range (a ``LinearScale`` over Unix timestamps)."""

    def __init__(self, domain: tuple[datetime, datetime], range_: tuple[float, float]) -> None:
        self.domain = domain
        self.range = range_
        self._linear = LinearScale((domain[0].timestamp(), domain[1].timestamp()), range_)

    def __call__(self, value: datetime) -> float:
        """Map a datetime value to a pixel position."""
        return self._linear(value.timestamp())


def _nice_step(rough_step: float) -> float:
    """Round a step size up to a "nice" 1/2/5 * 10^n value (classic nice-number tick algorithm)."""
    if rough_step <= 0:
        return 1.0
    magnitude = 10 ** math.floor(math.log10(rough_step))
    residual = rough_step / magnitude
    if residual < 1.5:
        nice = 1
    elif residual < 3:
        nice = 2
    elif residual < 7:
        nice = 5
    else:
        nice = 10
    return nice * magnitude


def _nice_linear_ticks(domain_min: float, domain_max: float, count: int) -> list[float]:
    """Generate round tick values spanning ``[domain_min, domain_max]`` (order-independent)."""
    low, high = sorted((domain_min, domain_max))
    if low == high:
        return [low]
    step = _nice_step((high - low) / max(count, 1))
    ticks = []
    value = math.ceil(low / step) * step
    while value <= high + step * 1e-9:
        ticks.append(round(value, 10))
        value += step
    return ticks


def make_ticks(scale: object, count: int = 5) -> list[object]:
    """Generate "nice" tick positions for the given scale (no text-width measurement).

    ``CategoricalScale`` returns every category, in order — categorical axes
    show all labels rather than a sampled subset.

    Raises:
        TypeError: if ``scale`` isn't a ``LinearScale``, ``CategoricalScale``, or ``TimeScale``.
    """
    if isinstance(scale, CategoricalScale):
        return list(scale.categories)
    if isinstance(scale, TimeScale):
        domain_min, domain_max = scale.domain
        numeric_ticks = _nice_linear_ticks(domain_min.timestamp(), domain_max.timestamp(), count)
        return [datetime.fromtimestamp(tick) for tick in numeric_ticks]
    if isinstance(scale, LinearScale):
        domain_min, domain_max = scale.domain
        return _nice_linear_ticks(domain_min, domain_max, count)
    raise TypeError(f"unsupported scale type for make_ticks: {type(scale).__name__}")
