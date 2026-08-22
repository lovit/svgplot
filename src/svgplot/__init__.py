"""svgplot: aesthetic, markdown-friendly SVG plotting for Python.

Design background: docs-research/00-overview.md.
"""

from __future__ import annotations

from svgplot.chart import Chart, Composition
from svgplot.charts import (
    areaplot,
    barplot,
    boxplot,
    ecdfplot,
    gaugeplot,
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

# ``Estimator`` comes from the private module rather than through ``svgplot.charts``: that
# package's ``__all__`` means "the sixteen chart functions", and two test registries derive
# themselves from it (``test_markdown_embedding``, ``test_charts_describe``). Re-exporting a
# type alias there made both of them believe a seventeenth chart had shipped.
from svgplot.charts._aggregate import Estimator
from svgplot.labels import LabelSpec
from svgplot.layout import add_caption, apply_size, column, facet, grid, row
from svgplot.theme import PRESETS, Theme, apply_context, parametric_theme
from svgplot.warnings import AggregationWarning, HeatmapSizeWarning, SvgplotWarning

__version__ = "0.1.0"

__all__ = [
    "PRESETS",
    "AggregationWarning",
    "Chart",
    "Composition",
    "Estimator",
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
    "gaugeplot",
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
