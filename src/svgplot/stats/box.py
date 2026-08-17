"""Box-plot statistics: quartiles, whiskers, outliers (pygal's 5 box_mode precedent, docs/research/01-pygal.md A7).

pygal's exact internal box_mode formulas are undocumented in this repo's research notes,
so each mode below is a clear, internally-consistent, standard-statistics interpretation
of the named method rather than a bit-for-bit port.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

MODES = ("extremes", "1.5IQR", "tukey", "stdev", "pstdev")


@dataclass(frozen=True)
class BoxStats:
    """Summary statistics for a single box-plot series."""

    median: float
    q1: float
    q3: float
    whisker_low: float
    whisker_high: float
    outliers: list[float]


def _percentile_linear(sorted_values: list[float], q: float) -> float:
    """Linear-interpolation percentile (the common/numpy-default method)."""
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    rank = q * (n - 1)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return sorted_values[lower]
    fraction = rank - lower
    return sorted_values[lower] + fraction * (sorted_values[upper] - sorted_values[lower])


def _tukey_hinges(sorted_values: list[float]) -> tuple[float, float]:
    """Tukey's hinges: median of the lower/upper half, excluding the overall median
    element for odd-length data (the classic "exclusive" hinge method)."""
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0], sorted_values[0]
    mid = n // 2
    lower_half = sorted_values[:mid]
    upper_half = sorted_values[-mid:]
    return statistics.median(lower_half), statistics.median(upper_half)


def box_stats(values: list[float], mode: str = "1.5IQR") -> BoxStats:
    """Compute median/quartiles/whiskers/outliers for a box plot.

    Raises:
        ValueError: if ``values`` is empty, ``mode`` isn't one of :data:`MODES`, any
            value isn't a finite number, or the ``stdev``/``pstdev`` computation itself
            overflows on extreme-but-finite input.
    """
    if not values:
        raise ValueError("values must not be empty")
    if mode not in MODES:
        raise ValueError(f"unknown box mode: {mode!r} (available: {MODES})")
    for value in values:
        try:
            finite = math.isfinite(value)
        except TypeError as error:
            raise ValueError(f"box_stats values must be numbers, got {value!r}") from error
        if not finite:
            raise ValueError(f"cannot compute box stats with a non-finite value: {value!r}")

    sorted_values = sorted(values)
    median = statistics.median(sorted_values)

    if mode == "tukey":
        q1, q3 = _tukey_hinges(sorted_values)
    else:
        q1 = _percentile_linear(sorted_values, 0.25)
        q3 = _percentile_linear(sorted_values, 0.75)

    if mode == "extremes":
        whisker_low, whisker_high, outliers = sorted_values[0], sorted_values[-1], []
    elif mode in ("1.5IQR", "tukey"):
        iqr = q3 - q1
        lower_fence = q1 - 1.5 * iqr
        upper_fence = q3 + 1.5 * iqr
        inside = [v for v in sorted_values if lower_fence <= v <= upper_fence]
        outliers = [v for v in sorted_values if v < lower_fence or v > upper_fence]
        whisker_low = min(inside) if inside else median
        whisker_high = max(inside) if inside else median
    else:  # stdev / pstdev
        try:
            mean = statistics.fmean(sorted_values)
            if len(sorted_values) == 1:
                spread = 0.0
            elif mode == "stdev":
                spread = statistics.stdev(sorted_values)
            else:
                spread = statistics.pstdev(sorted_values)
            whisker_low = mean - spread
            whisker_high = mean + spread
        except (OverflowError, statistics.StatisticsError) as error:
            raise ValueError(f"cannot compute {mode} box stats: {error}") from error
        outliers = [v for v in sorted_values if v < whisker_low or v > whisker_high]

    if not (math.isfinite(whisker_low) and math.isfinite(whisker_high)):
        raise ValueError(f"box stats whiskers must be finite, got low={whisker_low!r} high={whisker_high!r}")
    return BoxStats(median=median, q1=q1, q3=q3, whisker_low=whisker_low, whisker_high=whisker_high, outliers=outliers)
