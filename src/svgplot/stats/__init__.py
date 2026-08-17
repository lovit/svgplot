"""Statistical transforms: interpolation, histogram binning, box-plot statistics."""

from __future__ import annotations

from svgplot.stats.binning import histogram_bins
from svgplot.stats.box import box_stats
from svgplot.stats.interpolate import interpolate

__all__ = ["box_stats", "histogram_bins", "interpolate"]
