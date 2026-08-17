"""barplot — vertical/horizontal/grouped(dodge)/stacked bar charts (all one function, one mark family)."""

from __future__ import annotations

from svgplot.chart.base import Chart
from svgplot.theme.base import Theme


def barplot(
    data: object,
    x: str,
    y: str,
    hue: str | None = None,
    *,
    orient: str = "v",
    stacked: bool = False,
    theme: Theme | str | None = None,
) -> Chart:
    """Draw a bar chart. orient='v'|'h'; hue= without stacked triggers grouped (dodge) bars."""
    raise NotImplementedError
