"""pieplot — pie/donut charts (donut via inner_radius)."""

from __future__ import annotations

from svgplot.chart.base import Chart
from svgplot.theme.base import Theme


def pieplot(
    data: object,
    values: str,
    labels: str | None = None,
    *,
    inner_radius: float = 0.0,
    theme: Theme | str | None = None,
) -> Chart:
    """Draw a pie chart; inner_radius > 0 renders a donut."""
    raise NotImplementedError
