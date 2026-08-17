"""col=/row= faceting — groups data via svgplot.data.semantic and arranges the
resulting per-group charts with svgplot.layout.grid (docs/research/10-feature-matrix.md A1)."""

from __future__ import annotations

from collections.abc import Callable

from svgplot.chart.composition import Composition


def facet(
    plot_fn: Callable[..., object],
    data: object,
    col: str | None = None,
    row: str | None = None,
    **kwargs: object,
) -> Composition:
    """Call plot_fn once per col=/row= group and arrange the results in a grid."""
    raise NotImplementedError
