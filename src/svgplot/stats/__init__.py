"""Statistical transforms: interpolation, histogram binning, quantiles, box-plot statistics,
linear regression."""

from __future__ import annotations

from svgplot.stats.binning import histogram_bins
from svgplot.stats.box import BoxStats, box_stats
from svgplot.stats.interpolate import InterpolatedCurve, interpolate
from svgplot.stats.quantile import quantile, quantiles
from svgplot.stats.regression import LinearFit, RegressionBand, confidence_band, linear_fit

__all__ = [
    "BoxStats",
    "InterpolatedCurve",
    "LinearFit",
    "RegressionBand",
    "box_stats",
    "confidence_band",
    "histogram_bins",
    "interpolate",
    "linear_fit",
    "quantile",
    "quantiles",
]
