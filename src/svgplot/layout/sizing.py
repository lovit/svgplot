"""Two-mode sizing (fixed/responsive), replacing Bokeh's 8-value sizing_mode
for a markdown-embedded static document (docs/research/16-layout-vocabulary.md)."""

from __future__ import annotations

from svgplot.chart.base import Chart

SIZE_MODES = ("fixed", "responsive")


def apply_size(chart: Chart, mode: str = "fixed") -> Chart:
    """Set the chart's sizing mode: 'fixed' (explicit width/height) or
    'responsive' (viewBox + CSS max-width:100%)."""
    raise NotImplementedError
