"""Multi-chart composition: row/column/grid/caption/sizing/facet — docs/research/16-layout-vocabulary.md."""

from __future__ import annotations

from svgplot.layout.caption import add_caption
from svgplot.layout.facet import facet
from svgplot.layout.grid import column, grid, row
from svgplot.layout.sizing import apply_size

__all__ = ["add_caption", "apply_size", "column", "facet", "grid", "row"]
