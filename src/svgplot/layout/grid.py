"""row/column (1D) and grid (2D, span-aware) chart arrangement — Bokeh vocabulary
translated to a static two-layer model (docs/research/16-layout-vocabulary.md)."""

from __future__ import annotations

from svgplot.chart.base import Chart
from svgplot.chart.composition import Composition


def row(charts: list[Chart | None], spacing: int = 12) -> Composition:
    """Arrange charts in a single horizontal row. ``None`` entries render as empty cells."""
    raise NotImplementedError


def column(charts: list[Chart | None], spacing: int = 12) -> Composition:
    """Arrange charts in a single vertical column. ``None`` entries render as empty cells."""
    raise NotImplementedError


def grid(
    cells: list[list[Chart | None]] | list[tuple[Chart, int, int, int, int]],
    *,
    ncols: int | None = None,
    spacing: int = 12,
) -> Composition:
    """Arrange charts in a 2D grid. Accepts either a matrix of charts (None = empty cell)
    or a list of (chart, row, col, rowspan, colspan) tuples for span-aware placement."""
    raise NotImplementedError
