"""boxplot — box-and-whisker charts (statistics delegated to svgplot.stats.box)."""

from __future__ import annotations

from svgplot.chart.base import Chart
from svgplot.theme.base import Theme


def boxplot(
    data: object,
    x: str,
    y: str,
    *,
    mode: str = "1.5IQR",
    theme: Theme | str | None = None,
) -> Chart:
    """Draw a box plot from long-form data."""
    raise NotImplementedError
