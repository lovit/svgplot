"""svgplot: aesthetic, markdown-friendly SVG plotting for Python.

Design background: docs/research/00-overview.md.
"""

from __future__ import annotations

from svgplot.chart import Chart, Composition
from svgplot.charts import (
    areaplot,
    barplot,
    boxplot,
    ecdfplot,
    heatmap,
    histplot,
    kdeplot,
    lineplot,
    pieplot,
    radarplot,
    regplot,
    scatterplot,
    sparkline,
    treemap,
    violinplot,
)
from svgplot.labels import LabelSpec
from svgplot.layout import add_caption, apply_size, column, facet, grid, row
from svgplot.theme import PRESETS, Theme, apply_context, parametric_theme
from svgplot.warnings import HeatmapSizeWarning, SvgplotWarning

__version__ = "0.1.0"

__all__ = [
    "PRESETS",
    "Chart",
    "Composition",
    "HeatmapSizeWarning",
    "LabelSpec",
    "SvgplotWarning",
    "Theme",
    "__version__",
    "add_caption",
    "apply_context",
    "apply_size",
    "areaplot",
    "barplot",
    "boxplot",
    "column",
    "ecdfplot",
    "facet",
    "grid",
    "heatmap",
    "histplot",
    "kdeplot",
    "lineplot",
    "parametric_theme",
    "pieplot",
    "radarplot",
    "regplot",
    "row",
    "scatterplot",
    "sparkline",
    "treemap",
    "violinplot",
]
