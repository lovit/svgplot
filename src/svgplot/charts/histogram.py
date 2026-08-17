"""histplot — histograms with automatic binning (delegates to svgplot.stats.binning)."""

from __future__ import annotations

from svgplot.chart.base import Chart
from svgplot.theme.base import Theme


def histplot(
    data: object,
    x: str,
    hue: str | None = None,
    *,
    bins: str | int = "auto",
    theme: Theme | str | None = None,
) -> Chart:
    """Draw a histogram from long-form data with automatic binning."""
    raise NotImplementedError
