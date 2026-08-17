"""lineplot — line charts, including time-axis (a scales.TimeScale option, not a separate chart type)."""

from __future__ import annotations

from svgplot.chart.base import Chart
from svgplot.theme.base import Theme


def lineplot(
    data: object,
    x: str,
    y: str,
    hue: str | None = None,
    *,
    interpolate: str = "linear",
    theme: Theme | str | None = None,
) -> Chart:
    """Draw a line chart from long-form data."""
    raise NotImplementedError
