"""areaplot — filled area charts (fill_between-style), with an optional stacked mode."""

from __future__ import annotations

from svgplot.chart.base import Chart
from svgplot.theme.base import Theme


def areaplot(
    data: object,
    x: str,
    y: str,
    hue: str | None = None,
    *,
    stacked: bool = False,
    theme: Theme | str | None = None,
) -> Chart:
    """Draw a filled area chart from long-form data."""
    raise NotImplementedError
