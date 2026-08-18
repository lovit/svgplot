"""Statistical transforms: interpolation, histogram binning, quantiles, box-plot statistics."""

from __future__ import annotations

from svgplot.stats.binning import histogram_bins
from svgplot.stats.box import BoxStats, box_stats
from svgplot.stats.interpolate import InterpolatedCurve, interpolate
from svgplot.stats.quantile import quantile, quantiles

__all__ = [
    "BoxStats",
    "InterpolatedCurve",
    "box_stats",
    "histogram_bins",
    "interpolate",
    "quantile",
    "quantiles",
]
