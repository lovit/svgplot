"""svgplot: aesthetic, markdown-friendly SVG plotting for Python.

Design background: docs/research/00-overview.md.
"""

from __future__ import annotations

from svgplot.chart import Chart, Composition
from svgplot.charts import (
    areaplot,
    barplot,
    boxplot,
    histplot,
    lineplot,
    pieplot,
    scatterplot,
    treemap,
)
from svgplot.layout import add_caption, apply_size, column, facet, grid, row
from svgplot.theme import PRESETS, Theme, apply_context, parametric_theme

__version__ = "0.1.0"

__all__ = [
    "PRESETS",
    "Chart",
    "Composition",
    "Theme",
    "__version__",
    "add_caption",
    "apply_context",
    "apply_size",
    "areaplot",
    "barplot",
    "boxplot",
    "column",
    "facet",
    "grid",
    "histplot",
    "lineplot",
    "parametric_theme",
    "pieplot",
    "row",
    "scatterplot",
    "treemap",
]
