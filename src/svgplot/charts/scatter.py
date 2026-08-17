"""scatterplot — point charts with hue/size semantic channel mapping."""

from __future__ import annotations

from svgplot.chart.base import Chart
from svgplot.theme.base import Theme


def scatterplot(
    data: object,
    x: str,
    y: str,
    hue: str | None = None,
    size: str | None = None,
    *,
    theme: Theme | str | None = None,
) -> Chart:
    """Draw a scatter plot from long-form data."""
    raise NotImplementedError
