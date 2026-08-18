"""Statistical transforms: interpolation, histogram binning, quantiles, box-plot statistics,
kernel density estimation."""

from __future__ import annotations

from svgplot.stats.binning import histogram_bins
from svgplot.stats.box import BoxStats, box_stats
from svgplot.stats.interpolate import InterpolatedCurve, interpolate
from svgplot.stats.kde import BANDWIDTH_RULES, KdeCurve, kde
from svgplot.stats.quantile import quantile, quantiles

__all__ = [
    "BANDWIDTH_RULES",
    "BoxStats",
    "InterpolatedCurve",
    "KdeCurve",
    "box_stats",
    "histogram_bins",
    "interpolate",
    "kde",
    "quantile",
    "quantiles",
]
