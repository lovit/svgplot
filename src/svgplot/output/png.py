"""PNG raster export via an optional dependency (cairosvg), matching pygal's precedent
of keeping the core install light (docs/research/01-pygal.md A8)."""

from __future__ import annotations

from svgplot._svg import SvgDocument


def to_png(document: SvgDocument, path: str) -> None:
    """Rasterize an SvgDocument to a PNG file. Requires the ``png`` extra."""
    raise NotImplementedError
