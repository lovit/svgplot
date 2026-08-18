"""Chart-type functions — the primary public API surface (docs/research/11-api-syntax.md 권고안 B)."""

from __future__ import annotations

from svgplot.charts.area import areaplot
from svgplot.charts.bar import barplot
from svgplot.charts.box import boxplot
from svgplot.charts.ecdf import ecdfplot
from svgplot.charts.gauge import gaugeplot
from svgplot.charts.heatmap import heatmap
from svgplot.charts.histogram import histplot
from svgplot.charts.kde import kdeplot
from svgplot.charts.line import lineplot
from svgplot.charts.pie import pieplot
from svgplot.charts.radar import radarplot
from svgplot.charts.regression import regplot
from svgplot.charts.scatter import scatterplot
from svgplot.charts.sparkline import sparkline
from svgplot.charts.treemap import treemap
from svgplot.charts.violin import violinplot

__all__ = [
    "areaplot",
    "barplot",
    "boxplot",
    "ecdfplot",
    "gaugeplot",
    "heatmap",
    "histplot",
    "kdeplot",
    "lineplot",
    "pieplot",
    "radarplot",
    "regplot",
    "scatterplot",
    "sparkline",
    "treemap",
    "violinplot",
]
