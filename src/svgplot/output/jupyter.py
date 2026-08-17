"""Jupyter rich-display integration (``_repr_svg_``)."""

from __future__ import annotations

from svgplot._svg import SvgDocument


def repr_svg(document: SvgDocument) -> str:
    """Return the SVG string Jupyter uses to render a Chart/Composition inline."""
    raise NotImplementedError
