"""Automatic histogram binning (docs/research/10-feature-matrix.md A7).

The strategies are numpy's, reimplemented here rather than delegated. Delegating was one
import in one line, and it made ``numpy`` a required dependency of a package whose job is to
put an SVG in a markdown file -- every other statistics module here is pure stdlib, and
``stats/kde.py`` records the measurement behind that choice.

Reimplementing also settles something delegating could not. numpy's ``auto`` changed between
versions: it used to be ``min(fd, sturges)`` and in 2.5 it is
``min(max(fd, sqrt/2), sturges)``, a heuristic added to stop a spike in the data producing
thousands of bins. A package whose identity is "same input, same SVG" cannot have its bin
count depend on which numpy the reader happens to have installed.

The edges these produce are **bit-identical to numpy 2.5.2** over a corpus of 24,000
combinations -- 2,000 datasets across ten shapes (uniform, gaussian, constant, spiked, tiny,
huge, negative, integral, bimodal, exponential) and sizes 1 to 5,000, against all seven
strategies and five explicit counts. ``tests/test_stats_binning.py`` keeps a sample of that
comparison, skipped when numpy is absent.
"""

from __future__ import annotations

import math

from svgplot.stats.quantile import quantile

_MAX_BINS = 10_000
"""Sane upper bound on an explicit int ``bins`` count -- without this, e.g.
``bins=10**8`` returns ~800MB of edges from a single call, matching the spirit
of ``_MAX_PRECISION`` in ``stats.interpolate``."""

_STRATEGIES = ("auto", "fd", "doane", "scott", "rice", "sturges", "sqrt")


def _population_stdev(values: list[float]) -> float:
    """Standard deviation with ``ddof=0``, which is what ``numpy.std`` defaults to."""
    mean = math.fsum(values) / len(values)
    return math.sqrt(math.fsum((value - mean) ** 2 for value in values) / len(values))


def _bin_width(strategy: str, values: list[float], span: float) -> float:
    """The bin width a strategy asks for, or ``0.0`` for "one bin is enough".

    ``span`` is the data's own peak-to-peak, not the widened outer edges. The distinction only
    shows on constant data, where numpy widens the edges to +/-0.5 for the *linspace* but
    still hands the selectors a span of zero -- so they return zero and the chart gets one bin
    rather than five.
    """
    count = len(values)
    sturges = span / (math.log2(count) + 1.0)
    if strategy == "sturges":
        return sturges
    root = span / math.sqrt(count)
    if strategy == "sqrt":
        return root
    if strategy == "rice":
        return span / (2.0 * count ** (1 / 3))
    if strategy == "scott":
        return (24.0 * math.sqrt(math.pi) / count) ** (1 / 3) * _population_stdev(values)
    if strategy in ("fd", "auto"):
        ordered = sorted(values)
        spread = quantile(ordered, 0.75) - quantile(ordered, 0.25)
        freedman = 2.0 * spread * count ** (-1 / 3)
        if strategy == "fd":
            return freedman
        # Freedman-Diaconis is the most robust of these until the data has a spike, where its
        # inter-quartile spread collapses and the bin count runs to thousands. Half the sqrt
        # estimate is the floor numpy 2.5 added to stop that.
        return min(max(freedman, root / 2.0), sturges)
    # doane, the only one that looks at shape rather than spread.
    if count <= 2:
        return 0.0
    deviation = _population_stdev(values)
    if deviation == 0.0:
        return 0.0
    mean = math.fsum(values) / count
    skew = math.fsum(((value - mean) / deviation) ** 3 for value in values) / count
    correction = math.sqrt(6.0 * (count - 2) / ((count + 1.0) * (count + 3)))
    return span / (1.0 + math.log2(count) + math.log2(1.0 + abs(skew) / correction))


def _even_edges(low: float, high: float, count: int) -> list[float]:
    """``count + 1`` edges from ``low`` to ``high``, the way ``numpy.linspace`` lays them out.

    Accumulating ``low + index * step`` rather than adding ``step`` repeatedly, because the
    repeated addition drifts; and forcing the last edge to ``high`` rather than computing it,
    because ``low + count * step`` is not exactly ``high`` in binary floating point and a
    histogram whose last edge falls short of its own maximum drops that value.
    """
    if count < 1:
        return [low, high]
    step = (high - low) / count
    edges = [low + index * step for index in range(count + 1)]
    edges[-1] = high
    return edges


def histogram_bins(values: list[float], bins: str | int = "auto") -> list[float]:
    """Histogram bin edges for ``values``.

    ``bins`` is a count or one of :data:`_STRATEGIES`.

    Raises:
        ValueError: if ``values`` is empty or holds a non-numeric or non-finite value, if the
            span isn't finite (individually finite values, e.g. ``-1e308`` and ``1e308``, can
            still overflow), if ``bins`` isn't a ``str``/``int``, if an int ``bins`` exceeds
            :data:`_MAX_BINS`, or if a str ``bins`` isn't a known strategy.
    """
    if not values:
        raise ValueError("values must not be empty")
    if not isinstance(bins, str | int) or isinstance(bins, bool):
        raise ValueError(f"bins must be a string or int, got {bins!r}")
    if isinstance(bins, int) and bins > _MAX_BINS:
        raise ValueError(f"bins must be at most {_MAX_BINS}, got {bins}")
    if isinstance(bins, str) and bins not in _STRATEGIES:
        raise ValueError(f"bins must be an int or one of {', '.join(sorted(_STRATEGIES))}, got {bins!r}")
    for value in values:
        try:
            finite = math.isfinite(value)
        except TypeError as error:
            raise ValueError(f"values must be numbers, got {value!r}") from error
        if not finite:
            raise ValueError(f"cannot bin a non-finite value: {value!r}")
    span = max(values) - min(values)
    if not math.isfinite(span):
        raise ValueError(f"values span (max - min = {span!r}) must be finite")
    low, high = float(min(values)), float(max(values))
    if low == high:
        # A single distinct value has no width to divide. numpy widens by half a unit either
        # side so the bar has somewhere to be drawn.
        low, high = low - 0.5, high + 0.5
    if isinstance(bins, int):
        return _even_edges(low, high, bins)
    width = _bin_width(bins, values, span)
    return _even_edges(low, high, int(math.ceil((high - low) / width)) if width else 1)
